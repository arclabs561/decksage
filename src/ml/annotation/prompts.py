"""Canonical judge prompts, one per annotation task.

Why this module exists: the repository grew at least six pair-judge prompts
(`llm_annotator.SIMILARITY_PROMPT_BASE`, `scale_annotations.MODE_PROMPT`,
`annotate_diverse_pairs._build_annotation_prompt`, `multi_model_annotate.
ANNOTATION_PROMPT`, the two inline prompts in `annotation_convergence` and
`fill_eval_holes`) that disagree about the scale, the anchors, and whether the
order of the pair matters. Labels written by them are not comparable and the
prompt version is missing from most records.

Design rules encoded here (see docs/JUDGE-CALIBRATION.md and ADR-0001):

* one task per prompt; no prompt asks for four scores at once;
* the model must name a rubric band *and* a score inside that band, so the
  float cannot drift outside the anchor the model claims to be using;
* every task has an explicit ``uncertain`` answer, with no score;
* symmetric tasks carry a written order-swap instruction;
* the response is one strict JSON object with ``prompt_version``, and parsing
  rejects prose, fences, missing fields, extra fields, and out-of-band scores.

What a score does *not* mean: it is a rubric placement against the anchors in
this module, not a measured probability, not a human similarity rate, and not
transferable to another prompt version. Any downstream use must join on
``prompt_version``.

This module is additive. Nothing imports it by default; see
``.agents/reports/2026-10-28-judge-prompt-curation.md`` for the opt-in path.

Anchors are declared rubric anchors chosen by the prompt author from cards and
pairs that already exist in this repository's metadata and deck corpora. They
are not human labels. Each anchor names the facts it rests on, so a reviewer can
disagree with one score without re-deriving the prompt.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


PROMPT_VERSION = "judge-prompt-v1.0.0"

#: Legacy composite question (the old ``similarity_score`` field). ADR-0001
#: rejects it for new labels; kept so old corpora can be replayed in a
#: comparable form, and marked so a consumer can refuse it.
LEGACY_COMPOSITE_TASKS = frozenset({"similarity"})

#: Tasks whose answer must not depend on which card is listed first.
SYMMETRIC_TASKS = frozenset({"similarity", "substitute", "synergy", "meta"})

#: Legacy score field each task replaces. Recorded next to the label so a
#: migrated label cannot be silently read as a different question.
LEGACY_FIELD = {
    "similarity": "similarity_score",
    "substitute": "substitutability",
    "synergy": "synergy_score",
    "meta": "meta_relevance",
}

MIN_RATIONALE_CHARS = 40

DECK_DIMENSIONS = ("size_fit", "copy_limit", "role_coverage", "archetype_coherence")


class JudgeTask(StrEnum):
    SIMILARITY = "similarity"
    SUBSTITUTE = "substitute"
    SYNERGY = "synergy"
    META = "meta"
    ARCHETYPE = "archetype"
    DECK_QUALITY = "deck_quality"


class JudgeStatus(StrEnum):
    SCORED = "scored"
    UNCERTAIN = "uncertain"


# ---------------------------------------------------------------------------
# Rubric bands
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Band:
    """A half-open score band; the top band includes 1.0."""

    key: str
    low: float
    high: float
    definition: str

    @property
    def label(self) -> str:
        return f"{self.key} [{self.low:.2f}, {self.high:.2f}]"

    def contains(self, score: float, *, top: bool) -> bool:
        if top:
            return self.low <= score <= self.high
        return self.low <= score < self.high


SIMILARITY_BANDS = (
    Band(
        "unrelated",
        0.00,
        0.10,
        "Different function and different role; sharing a card type is not enough.",
    ),
    Band(
        "tangential",
        0.10,
        0.25,
        "Same broad category, different target, timing, cost tier or game-state role.",
    ),
    Band(
        "related_role",
        0.25,
        0.45,
        "Related role or archetype, but not the same function in a deck slot.",
    ),
    Band(
        "same_function",
        0.45,
        0.65,
        "Same function with a material difference in cost, timing or effect size.",
    ),
    Band(
        "near_substitute",
        0.65,
        0.85,
        "Same function and comparable efficiency; a player weighs trade-offs.",
    ),
    Band(
        "interchangeable",
        0.85,
        1.00,
        "Same function and near-identical effect; swapping changes little.",
    ),
)

SUBSTITUTE_BANDS = (
    Band(
        "not_a_substitute",
        0.00,
        0.10,
        "Could not fill the other card's slot in any deck the facts support.",
    ),
    Band(
        "edge_case",
        0.10,
        0.25,
        "Only in a narrow deck or format, and only with a compensating change.",
    ),
    Band(
        "partial",
        0.25,
        0.45,
        "Fills the same slot with a material loss (cost, timing, targets or stats).",
    ),
    Band(
        "same_slot", 0.45, 0.65, "Fills the same slot; the loss is real but a deck can absorb it."
    ),
    Band("close", 0.65, 0.85, "Fills the same slot with a minor, named difference."),
    Band("direct", 0.85, 1.00, "Direct replacement in the stated context; no other change needed."),
)

SYNERGY_BANDS = (
    Band("none", 0.00, 0.10, "No interaction beyond both being legal in the same format."),
    Band("incidental", 0.10, 0.30, "One card mildly helps the other; neither is chosen for it."),
    Band("moderate", 0.30, 0.55, "A real interaction that improves one line of play."),
    Band(
        "strong",
        0.55,
        0.80,
        "One card materially enables the other; decks include both on purpose.",
    ),
    Band(
        "engine",
        0.80,
        1.00,
        "A recorded loop or engine where the pair is the mechanism, not a preference.",
    ),
)

META_BANDS = (
    Band("absent", 0.00, 0.15, "Co-occurrence at or below what independent inclusion predicts."),
    Band("rare", 0.15, 0.35, "Some excess co-occurrence, small counts or one archetype."),
    Band("common", 0.35, 0.60, "Clearly more co-occurrence than inclusion alone predicts."),
    Band("staple_pair", 0.60, 0.85, "The pair is a regular package across decks of one archetype."),
    Band(
        "near_always", 0.85, 1.00, "In the supplied corpus the cards almost always appear together."
    ),
)

BANDS: dict[JudgeTask, tuple[Band, ...]] = {
    JudgeTask.SIMILARITY: SIMILARITY_BANDS,
    JudgeTask.SUBSTITUTE: SUBSTITUTE_BANDS,
    JudgeTask.SYNERGY: SYNERGY_BANDS,
    JudgeTask.META: META_BANDS,
}


def band_for(task: JudgeTask, score: float) -> Band:
    """Return the band a score falls in. Raises for unknown tasks or bad scores."""
    bands = BANDS[task]
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"score {score!r} outside [0, 1]")
    for index, band in enumerate(bands):
        if band.contains(score, top=index == len(bands) - 1):
            return band
    raise ValueError(f"score {score!r} fell in no band for {task}")


# ---------------------------------------------------------------------------
# Card facts and anchors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardFacts:
    """Exactly the facts the judge is allowed to use for one card."""

    name: str
    type_line: str
    text: str
    cost: str | None = None
    stats: str | None = None
    legality: str | None = None
    archetype: str | None = None

    def render(self) -> str:
        lines = [f"Name: {self.name}", f"Type: {self.type_line}"]
        if self.cost:
            lines.append(f"Cost: {self.cost}")
        if self.stats:
            lines.append(f"Stats: {self.stats}")
        if self.legality:
            lines.append(f"Legality: {self.legality}")
        if self.archetype:
            lines.append(f"Recorded archetype: {self.archetype}")
        lines.append(f"Rules text: {self.text}")
        return "\n".join(lines)


def card_facts_from_row(row: Mapping[str, Any]) -> CardFacts:
    """Build ``CardFacts`` from a ``card_attributes_*_enriched.csv`` row.

    Reads only columns that exist in the repository metadata; unknown or empty
    values stay ``None`` rather than being guessed.
    """
    name = str(row.get("name") or "").strip()
    if not name:
        raise ValueError("metadata row has no card name")
    text = str(row.get("oracle_text") or row.get("text") or row.get("effect") or "").strip()
    if not text:
        raise ValueError(f"metadata row for {name} has no rules text")

    stats_parts: list[str] = []
    if row.get("mana_cost"):
        cost = str(row["mana_cost"])
    else:
        cost = None
    if row.get("power") and row.get("toughness"):
        stats_parts.append(f"{row['power']}/{row['toughness']}")
    if row.get("hp"):
        stats_parts.append(f"HP {row['hp']}")
    if row.get("atk") and row.get("def_stat"):
        stats_parts.append(f"ATK/DEF {row['atk']}/{row['def_stat']}")
    if row.get("level_rank_link"):
        stats_parts.append(f"Level/Rank {row['level_rank_link']}")
    if row.get("regulation_mark"):
        stats_parts.append(f"Regulation mark {row['regulation_mark']}")

    return CardFacts(
        name=name,
        type_line=str(row.get("type_line") or row.get("type") or "unknown").strip(),
        text=text,
        cost=cost or None,
        stats=", ".join(stats_parts) or None,
        legality=str(row["legality"]) if row.get("legality") else None,
        archetype=str(row["archetype"]).strip() if row.get("archetype") else None,
    )


@dataclass(frozen=True)
class Anchor:
    """One rubric anchor: a real pair, the facts it rests on, and a band."""

    card_a: str
    card_b: str
    facts: str
    score: float
    why: str


# Anchors are keyed by (task, game). Facts come from
# data/processed/card_attributes_*_enriched.csv and, for co-occurrence counts,
# the deck files named in META_CORPORA. No fact here is invented.
ANCHORS: dict[tuple[JudgeTask, str], tuple[Anchor, ...]] = {
    (JudgeTask.SIMILARITY, "magic"): (
        Anchor(
            "Lightning Bolt",
            "Shock",
            "Both are {R} instants that deal damage to any target; 3 damage vs 2.",
            0.72,
            "Same type, cost and target; only the damage number differs.",
        ),
        Anchor(
            "Path to Exile",
            "Swords to Plowshares",
            "Both cost {W}, are instants, and exile target creature; the drawback is a "
            "basic land vs life equal to that creature's power.",
            0.88,
            "Same effect; the drawback is the only difference.",
        ),
        Anchor(
            "Counterspell",
            "Mana Leak",
            "Both counter a target spell for two mana; {U}{U} unconditionally vs {1}{U} "
            "unless that spell's controller pays {3}.",
            0.60,
            "Same function, materially different late-game reliability.",
        ),
        Anchor(
            "Lightning Bolt",
            "Counterspell",
            "Both are instants; one deals 3 damage to any target, the other counters a spell.",
            0.12,
            "Shared card type, different function.",
        ),
        Anchor(
            "Sol Ring",
            "Wrath of God",
            "An artifact for {1} that taps for {C}{C}, vs a {2}{W}{W} sorcery that destroys "
            "all creatures.",
            0.03,
            "No shared function, cost or role.",
        ),
        Anchor(
            "Brainstorm",
            "Ponder",
            "Both are one-mana blue card selection; Brainstorm is an instant that draws three "
            "then puts two back, Ponder is a sorcery that looks at three, may shuffle, then draws one.",
            0.55,
            "Same slot, different timing and outcome.",
        ),
    ),
    (JudgeTask.SIMILARITY, "pokemon"): (
        Anchor(
            "Ultra Ball",
            "Nest Ball",
            "Both are Item cards that search the deck for a Pokemon; Ultra Ball requires "
            "discarding 2 other cards and finds any Pokemon, Nest Ball finds a Basic Pokemon "
            "and puts it on the Bench.",
            0.58,
            "Same search role, different cost and target.",
        ),
        Anchor(
            "Professor's Research",
            "Iono",
            "Both are Supporters that draw; Professor's Research discards your hand and draws 7, "
            "Iono shuffles both hands into the deck and each player draws per prize taken.",
            0.38,
            "Same card type and rough purpose, different mechanism.",
        ),
        Anchor(
            "Charizard ex",
            "Radiant Charizard",
            "Charizard ex is a Stage 2 Tera ex with 330 HP; Radiant Charizard is a Basic Radiant "
            "with 160 HP. Both are Fire Charizard cards.",
            0.30,
            "Shared name and type, different stage and prize cost.",
        ),
        Anchor(
            "Arven",
            "Boss's Orders",
            "Both are Supporters; Arven searches an Item and a Pokemon Tool, Boss's Orders "
            "switches in a benched opponent's Pokemon.",
            0.12,
            "Same card type, unrelated effects.",
        ),
    ),
    (JudgeTask.SIMILARITY, "yugioh"): (
        Anchor(
            "Blue-Eyes White Dragon",
            "Blue-Eyes Alternative White Dragon",
            "Both are LIGHT Level 8 Dragon monsters with 3000 ATK / 2500 DEF and the recorded "
            "archetype Blue-Eyes; one is a Normal Monster, the other an Effect Monster that must "
            "first be Special Summoned by revealing Blue-Eyes White Dragon.",
            0.72,
            "Same stats and archetype, different summon path.",
        ),
        Anchor(
            "Ash Blossom & Joyous Spring",
            "Ghost Ogre & Snow Rabbit",
            "Both are Level 3 Tuner monsters with 0 ATK / 1800 DEF that are discarded from the "
            "hand as a Quick Effect; Ash Blossom negates add/summon-from-deck/mill effects, "
            "Ghost Ogre destroys a card that activated on the field.",
            0.42,
            "Same delivery and stats, different trigger.",
        ),
        Anchor(
            "Reinforcement of the Army",
            "Snake-Eye Ash",
            "Both add a monster from the deck to the hand; Reinforcement of the Army finds any "
            "Level 4 or lower Warrior, Snake-Eye Ash finds a Level 1 FIRE monster.",
            0.28,
            "Same search action, different legal targets.",
        ),
        Anchor(
            "Ash Blossom & Joyous Spring",
            "Nibiru, the Primal Being",
            "Both are hand-held disruption; Ash Blossom negates a search or summon effect, "
            "Nibiru tributes the field after the opponent summoned 5 or more monsters.",
            0.18,
            "Both disrupt, at different timings and for different reasons.",
        ),
    ),
    (JudgeTask.SUBSTITUTE, "magic"): (
        Anchor(
            "Lightning Bolt",
            "Shock",
            "Both are {R} instants dealing damage to any target; 3 vs 2 damage.",
            0.80,
            "Fills the same burn slot; the 1-damage loss is real but usually absorbed.",
        ),
        Anchor(
            "Path to Exile",
            "Swords to Plowshares",
            "Both cost {W} and exile target creature; the drawback differs.",
            0.88,
            "Same slot, interchangeable in most white decks.",
        ),
        Anchor(
            "Counterspell",
            "Mana Leak",
            "Two-mana counters; {U}{U} unconditional vs {1}{U} unless the controller pays {3}.",
            0.50,
            "Same slot early, not late.",
        ),
        Anchor(
            "Lightning Bolt",
            "Counterspell",
            "Damage spell vs counterspell, both instants.",
            0.02,
            "Different slot entirely.",
        ),
        Anchor(
            "Sol Ring",
            "Wrath of God",
            "Mana artifact vs creature sweeper.",
            0.00,
            "No deck asks for one in place of the other.",
        ),
    ),
    (JudgeTask.SUBSTITUTE, "pokemon"): (
        Anchor(
            "Ultra Ball",
            "Nest Ball",
            "Both are Item search cards; Ultra Ball discards 2 and finds any Pokemon, Nest Ball "
            "finds a Basic Pokemon onto the Bench.",
            0.50,
            "Same slot only when the target is a Basic; Ultra Ball is the broader card.",
        ),
        Anchor(
            "Professor's Research",
            "Iono",
            "Both are draw Supporters with different draw mechanics.",
            0.30,
            "Same Supporter slot, different outcome; a deck changes around the swap.",
        ),
        Anchor(
            "Charizard ex",
            "Radiant Charizard",
            "Stage 2 ex with 330 HP vs Basic Radiant with 160 HP.",
            0.10,
            "Different stage and prize cost; not a slot replacement.",
        ),
        Anchor(
            "Arven",
            "Boss's Orders",
            "Item+Tool search vs switching the opponent's Active.",
            0.03,
            "Unrelated Supporter effects.",
        ),
    ),
    (JudgeTask.SUBSTITUTE, "yugioh"): (
        Anchor(
            "Blue-Eyes White Dragon",
            "Blue-Eyes Alternative White Dragon",
            "Same LIGHT Level 8 Dragon stats and archetype; Alternative needs Blue-Eyes White "
            "Dragon revealed in hand to be Special Summoned.",
            0.60,
            "Same body and archetype, different summon requirement.",
        ),
        Anchor(
            "Ash Blossom & Joyous Spring",
            "Ghost Ogre & Snow Rabbit",
            "Both Level 3 Tuner hand traps, 0/1800, different trigger.",
            0.30,
            "Same delivery, different answer; sideboard-dependent.",
        ),
        Anchor(
            "Reinforcement of the Army",
            "Snake-Eye Ash",
            "Generic Level 4-or-lower Warrior search vs Level 1 FIRE search.",
            0.10,
            "Only overlaps in a Warrior/FIRE deck.",
        ),
        Anchor(
            "Ash Blossom & Joyous Spring",
            "Nibiru, the Primal Being",
            "Search negation vs summon-count board wipe.",
            0.05,
            "Different disruption slot.",
        ),
    ),
    (JudgeTask.SYNERGY, "magic"): (
        Anchor(
            "Sanguine Bond",
            "Exquisite Blood",
            "Sanguine Bond makes an opponent lose life when you gain life; Exquisite Blood gains "
            "you life when an opponent loses life. Recorded in the Commander Spellbook sample as "
            "an infinite lifegain/lifeloss loop.",
            0.95,
            "The pair is the loop mechanism.",
        ),
        Anchor(
            "Hullbreaker Horror",
            "Sol Ring",
            "Hullbreaker Horror returns a spell or nonland permanent when you cast a spell; "
            "Sol Ring taps for {C}{C}. Recorded in the same sample as infinite colorless mana.",
            0.75,
            "Sol Ring is the mana engine; Horror converts casts into repeated triggers.",
        ),
        Anchor(
            "Lightning Bolt",
            "Shock",
            "Two burn spells that do not interact with each other.",
            0.05,
            "Redundant, not complementary.",
        ),
        Anchor(
            "Lightning Bolt",
            "Wrath of God",
            "Bolt can finish a planeswalker or player after a sweeper, but neither enables the other.",
            0.10,
            "Incidental, not a reason to include either.",
        ),
    ),
    (JudgeTask.SYNERGY, "pokemon"): (
        Anchor(
            "Charizard ex",
            "Rare Candy",
            "Rare Candy evolves a Basic directly into a Stage 2 from hand. Recorded together in "
            "60-card Charizard Noctowl decks (2 Charizard ex, 4 Rare Candy).",
            0.60,
            "Rare Candy accelerates the Stage 2; Charizard ex is the payoff.",
        ),
        Anchor(
            "Ultra Ball",
            "Charizard ex",
            "Ultra Ball discards 2 cards to search any Pokemon; Charizard ex is a Stage 2 Pokemon.",
            0.35,
            "Search finds the piece; the interaction is real but generic.",
        ),
        Anchor(
            "Arven",
            "Rare Candy",
            "Arven searches an Item and a Pokemon Tool; Rare Candy is an Item.",
            0.45,
            "Arven can fetch Rare Candy, a real consistency line.",
        ),
        Anchor(
            "Professor's Research",
            "Iono",
            "Two draw Supporters; only one can be played per turn.",
            0.05,
            "Competes for the same slot.",
        ),
    ),
    (JudgeTask.SYNERGY, "yugioh"): (
        Anchor(
            "Snake-Eye Ash",
            "Snake-Eye Oak",
            "Both are Level 1 FIRE Pyro Snake-Eye monsters; Ash adds a Level 1 FIRE monster, Oak "
            "recovers a banished or Graveyard Level 1 FIRE monster. Recorded together in 2,822 "
            "Master Duel Meta decklists.",
            0.75,
            "Same engine, complementary search and recovery.",
        ),
        Anchor(
            "Snake-Eye Ash",
            "Original Sinful Spoils - Snake-Eye",
            "The Spell sends a face-up card to the Graveyard to Special Summon a Level 1 FIRE "
            "monster from hand or Deck; Ash is Level 1 FIRE.",
            0.70,
            "The Spell directly deploys Ash.",
        ),
        Anchor(
            "Ash Blossom & Joyous Spring",
            "Ghost Ogre & Snow Rabbit",
            "Two hand traps; no effect references the other.",
            0.05,
            "Redundant, not synergistic.",
        ),
        Anchor(
            "Ash Blossom & Joyous Spring",
            "Nibiru, the Primal Being",
            "Both interrupt the opponent, at different points; neither enables the other.",
            0.10,
            "Independent disruption.",
        ),
    ),
    (JudgeTask.META, "magic"): (
        Anchor(
            "Sanguine Bond",
            "Exquisite Blood",
            "In 11,607 recorded Moxfield Modern decklists: 13 contain Sanguine Bond, 15 contain "
            "Exquisite Blood, 9 contain both.",
            0.90,
            "Nine of fifteen Blood decks also run Bond.",
        ),
        Anchor(
            "Lightning Bolt",
            "Shock",
            "Same corpus: 2,047 Bolt, 48 Shock, 19 both.",
            0.35,
            "Excess co-occurrence exists but the counts are small.",
        ),
        Anchor(
            "Lightning Bolt",
            "Counterspell",
            "Same corpus: 2,047 Bolt, 1,210 Counterspell, 219 both.",
            0.15,
            "Co-occurrence is what independent inclusion predicts.",
        ),
    ),
    (JudgeTask.META, "pokemon"): (
        Anchor(
            "Charizard ex",
            "Rare Candy",
            "In 1,275 recorded Limitless decklists: 84 contain Charizard ex, 500 contain Rare "
            "Candy, 84 contain both.",
            0.80,
            "Every recorded Charizard ex deck runs Rare Candy.",
        ),
        Anchor(
            "Professor's Research",
            "Iono",
            "Same corpus: 121 Research, 835 Iono, 104 both.",
            0.35,
            "Both are common Supporters; the pair is not a package.",
        ),
        Anchor(
            "Ultra Ball",
            "Nest Ball",
            "Same corpus: 912 Ultra Ball, 718 Nest Ball, 524 both.",
            0.25,
            "Co-occurrence is close to independent inclusion.",
        ),
        Anchor(
            "Arven",
            "Boss's Orders",
            "Same corpus: 554 Arven, 1,034 Boss's Orders, 439 both.",
            0.20,
            "Common cards that happen to coexist.",
        ),
    ),
    (JudgeTask.META, "yugioh"): (
        Anchor(
            "Ash Blossom & Joyous Spring",
            "Snake-Eye Oak",
            "In 75,428 recorded Master Duel Meta decklists: 60,292 contain Ash Blossom, 2,833 "
            "contain Snake-Eye Oak, 2,822 contain both.",
            0.95,
            "Oak decks almost always run Ash Blossom.",
        ),
        Anchor(
            "Blue-Eyes White Dragon",
            "Blue-Eyes Alternative White Dragon",
            "Same corpus: 1,447 Blue-Eyes White Dragon, 139 Alternative, 139 both.",
            0.90,
            "Every recorded Alternative deck runs the original.",
        ),
        Anchor(
            "Ash Blossom & Joyous Spring",
            "Ghost Ogre & Snow Rabbit",
            "Same corpus: 60,292 Ash Blossom, 8,043 Ghost Ogre, 7,661 both.",
            0.30,
            "Ghost Ogre decks usually run Ash, but the reverse is not true.",
        ),
        Anchor(
            "Reinforcement of the Army",
            "Snake-Eye Ash",
            "Same corpus: 8,427 Reinforcement of the Army, 3,260 Snake-Eye Ash, 148 both.",
            0.10,
            "Below independent co-occurrence.",
        ),
    ),
}

#: Deck corpora behind the meta anchors. Recorded so a reviewer can recompute.
#: Paths are relative to the repository root; see PATHS for the canonical roots.
META_CORPORA = {
    "magic": "decks/decks_magic_moxfield_modern.jsonl (11,607 decks)",
    "pokemon": "decks/decks_pokemon_limitless.jsonl (1,275 decks)",
    "yugioh": "decks/decks_yugioh_masterduelmeta.jsonl (75,428 decks)",
}

#: Cards with a recorded card-level archetype in the Yu-Gi-Oh metadata.
ARCHETYPE_ANCHORS: dict[str, tuple[tuple[str, str | None, str], ...]] = {
    "yugioh": (
        ("Snake-Eye Ash", "Snake-Eye", "metadata archetype field"),
        ("Blue-Eyes White Dragon", "Blue-Eyes", "metadata archetype field"),
        ("Ash Blossom & Joyous Spring", None, "the metadata archive field is empty"),
    ),
}

#: Structural deck-quality anchors: real decklists from the repo, with the
#: counts recomputed from the file rather than remembered.
DECK_QUALITY_ANCHORS = (
    (
        "Rakdos evil (data/decks/decks_magic_moxfield_modern.jsonl)",
        "Main deck 59 cards, 22 distinct, max 4 copies, Modern.",
        "size_fit=1 (59 of 60, within 10%), copy_limit=2 (max 4)",
    ),
    (
        "Charizard Noctowl (data/decks/decks_pokemon_limitless.jsonl, "
        "deck_id limitless:699ac194c9dc8186f7609fa8:1)",
        "60 cards, 24 distinct, max 9 copies, archetype Charizard Noctowl.",
        "size_fit=2 (60 of 60), copy_limit=null (Pokemon has no generic 4-copy rule)",
    ),
)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Prompt:
    """A built prompt. ``pair_key`` is order-insensitive for symmetric tasks."""

    task: JudgeTask
    game: str
    system: str
    user: str
    prompt_version: str
    card_a: str
    card_b: str
    pair_key: str | None
    swapped: bool = False

    def as_messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user},
        ]


_COMMON_RULES = """\
You are a trading-card judge. Answer exactly one question about exactly one input.
Return one JSON object and nothing else: no prose, no markdown fence, no trailing text.

Rules that always apply:
1. Use only the facts in this prompt. Do not use remembered card text, price,
   tournament share, ban-list status, or "everyone knows" claims. If a fact you
   need is missing, answer with status "uncertain" and no score.
2. Choose a band first, then a score inside that band. A score outside the band
   you named is a malformed answer and will be rejected.
3. Confidence is your confidence in the placement, not the score itself.
4. The rationale must name the concrete facts that decided it. Do not restate
   the band definition.
5. Echo card_a and card_b exactly as given, and echo prompt_version exactly.
"""

_SYMMETRY_RULE = """\
Order: this question is symmetric. Pair (A, B) and pair (B, A) are the same
question and must receive the same score. Read the pair in both orders before
answering. If the two readings would differ by more than 0.05, answer
"uncertain" instead of picking one order.
"""

_SCHEMA_NOTE = """\
JSON schema (keys are required unless marked optional):
{schema}
"""

_WHAT_SCORE_MEANS = {
    JudgeTask.SIMILARITY: (
        "What the score means: a placement on this rubric for a generic 'how similar' "
        "question. It is NOT a substitute, synergy or meta judgment, and must not be used "
        "as one. This task is a legacy composite kept for replay; ADR-0001 says new labels "
        "should use the per-task prompts."
    ),
    JudgeTask.SUBSTITUTE: (
        "What the score means: could card B fill card A's slot in a deck, given the facts "
        "shown. It does NOT mean the cards are similar in the abstract, and does NOT mean "
        "B is better. It is not a price, format-legality, or sideboard recommendation."
    ),
    JudgeTask.SYNERGY: (
        "What the score means: do the two cards interact in a way that makes a deck want "
        "both. It does NOT mean they are substitutes, and does NOT mean they co-occur in "
        "recorded decks. Popularity is not synergy."
    ),
    JudgeTask.META: (
        "What the score means: how much more often the pair appears together than the two "
        "inclusion rates predict, in the corpus shown. It does NOT mean the cards are good, "
        "similar, or synergistic, and it is NOT a win-rate estimate. No corpus evidence "
        "means 'uncertain', never a guess."
    ),
    JudgeTask.ARCHETYPE: (
        "What the score means: a closed-set label from the candidate list. It does NOT "
        "mean the card is good in that archetype, and an unlisted archetype must not be "
        "invented; answer 'uncertain' or 'none' instead."
    ),
    JudgeTask.DECK_QUALITY: (
        "What the score means: a structural completeness score computed from the supplied "
        "counts, as a fraction of the applicable checks. It is NOT a power level, win rate, "
        "or 'is this deck good' judgment, and it must not be reported as one. A decklist "
        "without the counts needs 'uncertain'."
    ),
}


def _bands_block(task: JudgeTask) -> str:
    return "\n".join(f"- {band.label}: {band.definition}" for band in BANDS[task])


def _anchors_block(task: JudgeTask, game: str) -> str:
    anchors = ANCHORS.get((task, game), ())
    if not anchors:
        return (
            "No anchors are recorded for this game and task. If the facts do not settle the "
            "band, answer 'uncertain'."
        )
    lines = []
    for anchor in anchors:
        lines.append(
            f"- {anchor.card_a} vs {anchor.card_b} = {anchor.score:.2f}\n"
            f"  Facts: {anchor.facts}\n"
            f"  Why: {anchor.why}"
        )
    return "\n".join(lines)


def _meta_evidence_block(task: JudgeTask, game: str, evidence: Mapping[str, Any] | None) -> str:
    if task is not JudgeTask.META:
        return ""
    if not evidence:
        return (
            "Corpus evidence: none supplied. Do not estimate co-occurrence from card names; "
            'answer with status "uncertain".'
        )
    return (
        "Corpus evidence (supplied, use these numbers and nothing else):\n"
        f"- Corpus: {evidence.get('corpus', 'unspecified')}\n"
        f"- Decks containing card A: {evidence.get('decks_with_a')}\n"
        f"- Decks containing card B: {evidence.get('decks_with_b')}\n"
        f"- Decks containing both: {evidence.get('decks_with_both')}\n"
        f"- Decks in corpus: {evidence.get('deck_total')}"
    )


def _pair_schema(task: JudgeTask) -> str:
    return json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "task": str(task),
            "status": "one of: scored, uncertain",
            "band": "one of: "
            + ", ".join(band.key for band in BANDS[task])
            + " (null when uncertain)",
            "score": "number in [0, 1] inside band (null when uncertain)",
            "confidence": "number in [0, 1]",
            "rationale": f"string, at least {MIN_RATIONALE_CHARS} characters",
            "card_a": "string, echoes the prompt",
            "card_b": "string, echoes the prompt",
            "differences": "list of 1-3 strings (empty when uncertain)",
        },
        indent=2,
    )


def _archetype_schema() -> str:
    return json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "task": "archetype",
            "status": "one of: scored, uncertain",
            "label": "one of the candidate labels, or null",
            "confidence": "number in [0, 1]",
            "rationale": f"string, at least {MIN_RATIONALE_CHARS} characters",
            "card_a": "string, echoes the prompt",
        },
        indent=2,
    )


def _deck_schema() -> str:
    return json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "task": "deck_quality",
            "status": "one of: scored, uncertain",
            "dimensions": dict.fromkeys(DECK_DIMENSIONS, "0, 1, 2 or null"),
            "confidence": "number in [0, 1]",
            "rationale": f"string, at least {MIN_RATIONALE_CHARS} characters",
        },
        indent=2,
    )


def build_prompt(
    task: JudgeTask | str,
    card_a: CardFacts,
    card_b: CardFacts | None,
    *,
    game: str,
    swap: bool = False,
    evidence: Mapping[str, Any] | None = None,
    candidates: Sequence[str] | None = None,
    deck_summary: Mapping[str, Any] | None = None,
) -> Prompt:
    """Build the canonical prompt for one task.

    ``swap`` reverses the two cards for a symmetric task, keeping every other
    byte identical, so an order-swap probe compares like with like.
    """
    task = JudgeTask(task)
    game = game.lower()

    if task in (JudgeTask.ARCHETYPE, JudgeTask.DECK_QUALITY):
        if swap:
            raise ValueError(f"{task} is not a card-pair task; swap is meaningless")
        return _build_single_input_prompt(
            task,
            card_a,
            game=game,
            candidates=candidates,
            deck_summary=deck_summary,
        )

    if card_b is None:
        raise ValueError(f"{task} needs two cards")
    if swap and task not in SYMMETRIC_TASKS:
        raise ValueError(f"{task} is not symmetric; swap is not defined")
    first, second = (card_b, card_a) if swap else (card_a, card_b)
    pair_key = " | ".join(sorted((card_a.name, card_b.name)))

    schema = _pair_schema(task)
    system = _COMMON_RULES + (_SYMMETRY_RULE if task in SYMMETRIC_TASKS else "")
    user = "\n\n".join(
        part
        for part in (
            f"Question ({task}): {_QUESTION[task]}",
            f"Game: {game}",
            f"Card A:\n{first.render()}",
            f"Card B:\n{second.render()}",
            _meta_evidence_block(task, game, evidence),
            "Rubric bands:\n" + _bands_block(task),
            "Anchors (declared rubric anchors, not human labels):\n" + _anchors_block(task, game),
            _WHAT_SCORE_MEANS[task],
            _SCHEMA_NOTE.format(schema=schema),
        )
        if part
    )
    return Prompt(
        task=task,
        game=game,
        system=system,
        user=user,
        prompt_version=PROMPT_VERSION,
        card_a=first.name,
        card_b=second.name,
        pair_key=pair_key,
        swapped=swap,
    )


_QUESTION = {
    JudgeTask.SIMILARITY: "how similar are these two cards, on this rubric?",
    JudgeTask.SUBSTITUTE: "could card B replace card A in a deck that runs card A, "
    "without other changes?",
    JudgeTask.SYNERGY: "do these two cards interact in a way that makes a deck want both?",
    JudgeTask.META: "how much more often do these two cards appear together than their "
    "individual inclusion rates predict?",
}


def _build_single_input_prompt(
    task: JudgeTask,
    card: CardFacts,
    *,
    game: str,
    candidates: Sequence[str] | None,
    deck_summary: Mapping[str, Any] | None,
) -> Prompt:
    if task is JudgeTask.ARCHETYPE:
        if not candidates:
            raise ValueError("archetype prompt needs a closed candidate list")
        anchors = ARCHETYPE_ANCHORS.get(game, ())
        if anchors:
            anchor_text = "\n".join(
                f"- {name} -> {label if label else 'none'} ({source})"
                for name, label, source in anchors
            )
        else:
            anchor_text = (
                "No card-level archetype labels are recorded for this game. Answer 'uncertain' "
                "unless the card text itself names one of the candidates."
            )
        schema = _archetype_schema()
        body = [
            "Question (archetype): which candidate archetype does this card belong to?",
            f"Game: {game}",
            f"Candidates (closed set): {', '.join(candidates)}",
            f"Card:\n{card.render()}",
            "Anchors:\n" + anchor_text,
            _WHAT_SCORE_MEANS[task],
            _SCHEMA_NOTE.format(schema=schema),
        ]
        return Prompt(
            task=task,
            game=game,
            system=_COMMON_RULES,
            user="\n\n".join(body),
            prompt_version=PROMPT_VERSION,
            card_a=card.name,
            card_b="",
            pair_key=None,
        )

    if not deck_summary:
        raise ValueError("deck_quality prompt needs a deck summary")
    summary_lines = "\n".join(f"- {key}: {value}" for key, value in deck_summary.items())
    anchor_text = "\n".join(
        f"- {name}: {facts} -> {levels}" for name, facts, levels in DECK_QUALITY_ANCHORS
    )
    body = [
        "Question (deck_quality): score structural completeness from the supplied counts.",
        f"Game: {game}",
        f"Deck summary:\n{summary_lines}",
        "Dimension rules (apply mechanically; null when the inputs are absent):",
        "- size_fit: 2 when total_cards equals expected_size; 1 when within 10%; else 0.",
        "- copy_limit: 2 when max_copies is at or below the game's limit; 1 when at most "
        "limit+2; else 0. null when the game has no generic copy limit (Pokemon) or "
        "max_copies is absent.",
        "- role_coverage: 2 when at least 3 distinct roles have a non-zero count; 1 when 1-2; "
        "0 when none. null when role_counts is absent.",
        "- archetype_coherence: 2 when an archetype is supplied and at least 60% of cards "
        "carry it; 1 when an archetype is supplied; 0 when none. null when absent.",
        "Anchors (real decklists, counts recomputed from the repo file):\n" + anchor_text,
        _WHAT_SCORE_MEANS[task],
        _SCHEMA_NOTE.format(schema=_deck_schema()),
    ]
    return Prompt(
        task=task,
        game=game,
        system=_COMMON_RULES,
        user="\n\n".join(body),
        prompt_version=PROMPT_VERSION,
        card_a=card.name,
        card_b="",
        pair_key=None,
    )


# ---------------------------------------------------------------------------
# Strict response models
# ---------------------------------------------------------------------------


class JudgeResponseError(ValueError):
    """A model response was not a valid canonical answer."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _PairPayload(_StrictModel):
    prompt_version: str
    task: str
    status: str
    band: str | None = None
    score: float | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str
    card_a: str
    card_b: str
    differences: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def status_shape(self) -> _PairPayload:
        if self.status == JudgeStatus.SCORED:
            if self.band is None or self.score is None:
                raise ValueError("scored responses need both band and score")
        elif self.status == JudgeStatus.UNCERTAIN:
            if self.band is not None or self.score is not None:
                raise ValueError("uncertain responses must not carry a band or score")
        else:
            raise ValueError(f"status must be 'scored' or 'uncertain', got {self.status!r}")
        return self


class _ArchetypePayload(_StrictModel):
    prompt_version: str
    task: str
    status: str
    label: str | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str
    card_a: str


class _DeckPayload(_StrictModel):
    prompt_version: str
    task: str
    status: str
    dimensions: dict[str, int | None]
    confidence: float = Field(ge=0, le=1)
    rationale: str


@dataclass(frozen=True)
class PairLabel:
    """A validated pair label. ``score`` is None exactly when uncertain."""

    task: JudgeTask
    game: str
    status: JudgeStatus
    band: Band | None
    score: float | None
    confidence: float
    rationale: str
    differences: tuple[str, ...]
    card_a: str
    card_b: str
    prompt_version: str

    def as_legacy_record(self) -> dict[str, Any]:
        """Shape for the old v2 files, with everything needed to audit it."""
        record: dict[str, Any] = {
            "query": self.card_a,
            "candidate": self.card_b,
            "prompt_version": self.prompt_version,
            "task": str(self.task),
            "judge_status": str(self.status),
            "judge_band": self.band.key if self.band else None,
            "judge_confidence": self.confidence,
            "reasoning": self.rationale,
        }
        field = LEGACY_FIELD.get(str(self.task))
        if field:
            record[field] = self.score
        return record


@dataclass(frozen=True)
class ArchetypeLabel:
    task: JudgeTask
    game: str
    status: JudgeStatus
    label: str | None
    confidence: float
    rationale: str
    card: str
    prompt_version: str


@dataclass(frozen=True)
class DeckQualityLabel:
    task: JudgeTask
    game: str
    status: JudgeStatus
    dimensions: Mapping[str, int | None]
    score: float | None
    confidence: float
    rationale: str
    prompt_version: str


def _load_json_object(text: str) -> dict[str, Any]:
    """Parse exactly one JSON object. Prose, fences and arrays are rejected."""
    stripped = text.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        raise JudgeResponseError("response is not a bare JSON object")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise JudgeResponseError(f"response is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise JudgeResponseError("response JSON is not an object")
    return payload


def _check_common(
    payload: Mapping[str, Any], prompt: Prompt, model: type[_StrictModel]
) -> _StrictModel:
    try:
        parsed = model.model_validate(payload)
    except ValidationError as exc:
        raise JudgeResponseError(
            f"response does not match the schema: {exc.errors()[0]['msg']}"
        ) from exc
    if parsed.prompt_version != prompt.prompt_version:
        raise JudgeResponseError(
            f"prompt_version {parsed.prompt_version!r} != {prompt.prompt_version!r}"
        )
    if parsed.task != str(prompt.task):
        raise JudgeResponseError(f"task {parsed.task!r} != {prompt.task!s}")
    if len(parsed.rationale.strip()) < MIN_RATIONALE_CHARS:
        raise JudgeResponseError("rationale is too short to audit")
    return parsed


def parse_pair_label(text: str, prompt: Prompt) -> PairLabel:
    """Validate a pair-task response against the prompt that produced it."""
    if prompt.task not in BANDS:
        raise ValueError(f"{prompt.task} is not a pair task")
    payload = _load_json_object(text)
    parsed = _check_common(payload, prompt, _PairPayload)
    assert isinstance(parsed, _PairPayload)

    if parsed.card_a != prompt.card_a or parsed.card_b != prompt.card_b:
        raise JudgeResponseError(
            f"echoed cards ({parsed.card_a!r}, {parsed.card_b!r}) != "
            f"({prompt.card_a!r}, {prompt.card_b!r})"
        )

    status = JudgeStatus(parsed.status)
    band: Band | None = None
    score: float | None = None
    if status is JudgeStatus.SCORED:
        assert parsed.band is not None and parsed.score is not None
        bands = BANDS[prompt.task]
        matches = [candidate for candidate in bands if candidate.key == parsed.band]
        if not matches:
            raise JudgeResponseError(f"unknown band {parsed.band!r} for {prompt.task}")
        band = matches[0]
        top = band is bands[-1]
        if not band.contains(parsed.score, top=top):
            raise JudgeResponseError(
                f"score {parsed.score:.3f} is outside the declared band {band.label}"
            )
        score = parsed.score
        if not 1 <= len([item for item in parsed.differences if item.strip()]) <= 3:
            raise JudgeResponseError("scored responses need 1-3 non-empty differences")

    return PairLabel(
        task=prompt.task,
        game=prompt.game,
        status=status,
        band=band,
        score=score,
        confidence=parsed.confidence,
        rationale=parsed.rationale.strip(),
        differences=tuple(item.strip() for item in parsed.differences if item.strip()),
        card_a=parsed.card_a,
        card_b=parsed.card_b,
        prompt_version=parsed.prompt_version,
    )


def parse_archetype_label(
    text: str, prompt: Prompt, *, candidates: Sequence[str]
) -> ArchetypeLabel:
    """Validate a closed-set archetype response."""
    if prompt.task is not JudgeTask.ARCHETYPE:
        raise ValueError("parse_archetype_label needs an archetype prompt")
    payload = _load_json_object(text)
    parsed = _check_common(payload, prompt, _ArchetypePayload)
    assert isinstance(parsed, _ArchetypePayload)

    if parsed.card_a != prompt.card_a:
        raise JudgeResponseError(f"echoed card {parsed.card_a!r} != {prompt.card_a!r}")
    status = JudgeStatus(parsed.status)
    if status is JudgeStatus.SCORED:
        if parsed.label not in candidates:
            raise JudgeResponseError(f"label {parsed.label!r} is not in the candidate set")
    elif parsed.label is not None:
        raise JudgeResponseError("uncertain archetype responses must have label null")

    return ArchetypeLabel(
        task=prompt.task,
        game=prompt.game,
        status=status,
        label=parsed.label,
        confidence=parsed.confidence,
        rationale=parsed.rationale.strip(),
        card=parsed.card_a,
        prompt_version=parsed.prompt_version,
    )


def parse_deck_quality_label(text: str, prompt: Prompt) -> DeckQualityLabel:
    """Validate a deck-quality response and compute the score from its levels.

    The scalar is derived here, not written by the model, so the number is a
    function of the four auditable levels.
    """
    if prompt.task is not JudgeTask.DECK_QUALITY:
        raise ValueError("parse_deck_quality_label needs a deck_quality prompt")
    payload = _load_json_object(text)
    parsed = _check_common(payload, prompt, _DeckPayload)
    assert isinstance(parsed, _DeckPayload)

    if set(parsed.dimensions) != set(DECK_DIMENSIONS):
        raise JudgeResponseError(f"dimensions must be exactly {list(DECK_DIMENSIONS)}")
    for key, value in parsed.dimensions.items():
        if value is not None and value not in (0, 1, 2):
            raise JudgeResponseError(f"dimension {key} must be 0, 1, 2 or null, got {value!r}")

    status = JudgeStatus(parsed.status)
    score: float | None = None
    if status is JudgeStatus.SCORED:
        levels = [value for value in parsed.dimensions.values() if value is not None]
        if not levels:
            raise JudgeResponseError("scored responses need at least one applicable dimension")
        score = round(sum(levels) / (2 * len(levels)), 4)
    else:
        if any(value is not None for value in parsed.dimensions.values()):
            raise JudgeResponseError("uncertain responses must have all dimensions null")

    return DeckQualityLabel(
        task=prompt.task,
        game=prompt.game,
        status=status,
        dimensions=dict(parsed.dimensions),
        score=score,
        confidence=parsed.confidence,
        rationale=parsed.rationale.strip(),
        prompt_version=parsed.prompt_version,
    )


#: Opt-in flag name a future runner can read. Nothing reads it today.
OPT_IN_ENV = "DECKSAGE_CANONICAL_JUDGE_PROMPTS"


def emit_anchor_pairs() -> list[dict[str, str]]:
    """Flatten the pair anchors into ``judge_probe.py`` JSONL rows.

    Only the card names are emitted: the probe then measures how the judge's
    order behaviour treats this anchor set, without pretending that the probe's
    rubric is the canonical prompt. The recorded facts stay in ``ANCHORS``.
    """
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for (task, game), anchors in ANCHORS.items():
        for anchor in anchors:
            key = (anchor.card_a, anchor.card_b)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "query": anchor.card_a,
                    "candidate": anchor.card_b,
                    "task": str(task),
                    "game": game,
                }
            )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Canonical judge prompt utilities")
    parser.add_argument(
        "--emit-anchors",
        action="store_true",
        help="write the recorded pair anchors as judge_probe.py JSONL to stdout",
    )
    args = parser.parse_args(argv)
    if not args.emit_anchors:
        parser.error("nothing to do; pass --emit-anchors")
    for row in emit_anchor_pairs():
        print(json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ANCHORS",
    "ARCHETYPE_ANCHORS",
    "BANDS",
    "DECK_DIMENSIONS",
    "DECK_QUALITY_ANCHORS",
    "LEGACY_COMPOSITE_TASKS",
    "LEGACY_FIELD",
    "META_CORPORA",
    "MIN_RATIONALE_CHARS",
    "OPT_IN_ENV",
    "PROMPT_VERSION",
    "SYMMETRIC_TASKS",
    "Anchor",
    "ArchetypeLabel",
    "Band",
    "CardFacts",
    "DeckQualityLabel",
    "JudgeResponseError",
    "JudgeStatus",
    "JudgeTask",
    "PairLabel",
    "Prompt",
    "band_for",
    "build_prompt",
    "card_facts_from_row",
    "emit_anchor_pairs",
    "main",
    "parse_archetype_label",
    "parse_deck_quality_label",
    "parse_pair_label",
]
