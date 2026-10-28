# Label sources

Potential label sources and the proxies they might provide. Source-specific
terms and verdicts below are historical notes unless independently verified;
they do not establish permission to ingest or redistribute data. Companion to
ADR-0001, ADR-0002 and `JUDGE-CALIBRATION.md`.

## Construct first, source second

"Synergy" can mix combo, theme fit, role complement and meta pairing;
"substitute" can mix same-role replacement, budget downgrade, functional
reprint and meta call. Experiment 0027 reports low agreement on a specific
Magic multi-judge sample; agreement alone does not identify its cause or
establish agreement for other tasks or datasets.

Splitting the constructs is a prerequisite. No source will validate a label it
is not labelling, and no proxy comparison is interpretable while one field
answers four questions.

## The trap to avoid

EDHREC lift, MTGGoldfish archetypes, Limitless and Master Duel Meta look like
new signals. Most are deck co-occurrence with extra steps: they are computed
from decklists, which this project already has. Co-occurrence measures
complement and popularity, not replacement.

The second trap is mining "swap X for Y" at scale. It is a scalpel for building
a gold set, not a shovel for training data: volume collapses after
deduplication and conditionality ("on a budget", "against control") is the main
error source.

## What labels each source really contains

| Source | Label | Access | Terms | Main bias | Verdict |
|---|---|---|---|---|---|
| EDHREC precon upgrade guides | substitute (cut/add) | HTML/JSON | personal, non-commercial, no copying | precon-only, Commander | trial, licence first |
| Archidekt maybeboard + deck help | substitute, completion | undocumented API | personal, non-commercial | casual skew, "considered" not "replaced" | trial, licence first |
| Moxfield maybeboard, sideboard, primers | substitute, completion | undocumented API | automated access prohibited | view popularity | trial, partner only |
| CubeCobra changelogs | substitute inside a cube | public API | `ai-train=no` | idiosyncratic designers | evaluation only |
| Commander Spellbook | synergy (explicit combos) | [API and bulk export](https://spacecowmedia.github.io/commander-spellbook-backend/api.html) | data reuse terms unverified | combo/cEDH bias | research-only sample |
| Scryfall Tagger / oracle tags | card role | REST + daily bulk | no repackage | community inconsistency | adopt |
| MTGJSON | role, legality, prices | [bulk](https://www.mtgjson.com/downloads/all-files/) | [license page](https://www.mtgjson.com/license/) contains website-use terms; data rights not assessed | no functional labels | review before use |
| Wizards B&R, Konami F&L, Pokemon rotation | substitute via shocks | HTML/RSS | official facts | sparse, confounded by reprints | adopt as event anchors |
| MTGJSON prices, MTGStocks | substitute via market | bulk / undocumented | source-specific terms unverified | supply shocks dominate | event studies only |
| 17Lands public datasets | preference and performance | [published files](https://www.17lands.com/public_datasets) | reuse terms not verified in this audit | Limited only, skill skew | research, Limited |
| MTG cards similarity dataset | similarity proxy | [dataset card](https://huggingface.co/datasets/philipp-zettl/mtg_cards-2025-04-04) | rights and reuse unverified | labels automatically annotated; method not documented on the card | research only, not human gold |
| Limitless API | meta, completion | official API | attribution; redistribution unclear | top-cut bias | adopt |
| YGOPRODeck API | card, meta | 20 req/s | no explicit licence, Konami IP | netdecking, MD/TCG mix | adopt for card data |
| Yugipedia Card Tips | synergy (explicit relations) | MediaWiki | CC BY-SA | speculative, obsolete combos | adopt |
| Master Duel Meta | meta, combos | HTML + undocumented API | none stated | digital != paper | trial |
| MTGTop8, MTGGoldfish, TappedOut | meta | HTML | Goldfish/TappedOut prohibit automated use | selection | reject without licence |
| r/EDH, r/spikes, r/PokemonTCG, r/yugioh | substitute, synergy in prose | Reddit API | licence required for commercial use | upvote bias, self-selection | trial, licence only |
| YouTube, Discord, podcasts | none usable | no archive / prohibited | no scraping | entertainment | reject |
| Marketplace reviews, StackExchange, Blogatog | none or thin | varies | varies | not card function | reject |

Check source-specific terms and the project publishing boundary before using
or redistributing data. Preserve provenance for derived labels.

## Substitution: the task with no good public proxy

Ranked by density and directness:

1. EDHREC precon cut/add lists: revealed removals when players upgrade precons.
   Sets, not one-to-one pairs, and Commander only.
2. Maybeboards (Archidekt, Moxfield): "considered but not included" in roughly
   a third of recent decks. Slot competition, not a swap, until you snapshot
   decks weekly and diff them: a removal in the same edit as an addition is a
   direct swap pair. That diff is the highest-value construction here.
3. Archidekt deck-help requests: explicit "what do I cut, what replaces it".
   Low volume, high precision, ideal gold-set generator.
4. Sideboards: matchup-conditional replacement, requires pairing by role.
5. Cube changelogs: dated card-out/card-in, clean but cube-specific.
6. Ban and rotation shocks: causal and covering all three games, sparse.
7. Budget-alternative articles: literal "X instead of Y", low volume, high
   precision.

A framing that needs no new labels at all: substitution as **negative
co-occurrence plus role similarity**. Cards that rarely appear together, but
have similar inclusion distributions across commanders plus similar role tags,
cost and colour, are candidate substitutes. Maybeboards and precon cuts then
supply positives. This uses data already on disk.

## Synergy: better than raw co-occurrence

Commander Spellbook for explicit combos; Yugipedia Card Tips for explicit
"searched by / summoned by / used with" relations; Master Duel Meta combos and
counters; EDHREC lift as base-rate-normalised co-occurrence; cube inclusion as
curated synergy; causal language in primers ("because", "enables").

The correct co-occurrence baseline to beat is lift or PPMI with smoothing and a
minimum support, stratified by commander or archetype. Raw counts conflate
staple with synergy.

## Validation slice: 60 queries in one day

60 queries stratified 15 substitute, 15 synergy, 10 meta, 10 completion, 10
search. Each query: seed plus 8 to 12 candidates drawn from heterogeneous pools
(co-occurrence, maybeboard, text-mined, tag/role, price-event, random
negatives). Two annotators, 20 percent overlap, alpha reported per task and per
sub-type. Roughly 600 to 700 judgments, three to four hours.

Proxies measurable in the same day, each compared against the co-occurrence
baseline with paired bootstrap confidence intervals:

| Proxy | What it proves if it wins |
|---|---|
| Maybeboard overlap | "considered" sets capture substitution |
| Sideboard co-occurrence | sideboards encode situational replacements |
| Precon cut/add | structured cuts beat prose mining |
| Text-mined swaps | high precision proves gold-set value |
| Tag Jaccard + cost/colour/type | most of substitution is role matching |
| Price event abnormal return | market reveals causal substitutes on shock events |
| 17Lands pick order | Limited preference, expected to generalise weakly |

Decision rule: adopt a proxy at +0.05 AUC over the baseline with a confidence
interval excluding zero and at least 20 percent query coverage. Adopt a text
rule only at precision 0.8 or better on at least 20 audited pairs.

## Scraping policy

Scraping yields evidence, not truth. Nothing becomes a label without passing
the verification slice above.

- **Registry before crawler.** One entry per source: URL pattern, access method,
  terms note, rate limit, last fetch, content hash, and which label types it may
  produce. This is what makes the publishing boundary enforceable.
- **Snapshots, not copies.** Store the fetch hash and date with every derived
  label; keep the corpus out of git and out of any redistributed artifact.
- **Provenance on every candidate label:** `source_url`, `fetched_at`,
  `extractor`, `prompt_version`, `confidence`. Same shape as judge provenance.
- **Politeness:** robots.txt, one request at a time per host, conditional GETs,
  no auth-walled content.
- **Licence gate:** a source in the "licence first" column may be trialled on a
  small sample for internal evaluation, and must not enter training or a
  published artifact until permission is recorded in the registry.

## Cheap extraction and calibration

Extraction and probe runs are high-volume and low-stakes per call, so they run
on a flash-tier model with credentials resolved at process start, never on
disk. See `JUDGE-CALIBRATION.md` for the `op` invocation, the per-pair cost, and
the three calibration techniques.

## Ranked next steps

1. Review the existing `config/label_sources.toml` registry against primary
   sources, including source-specific reuse terms and attribution. Its current
   classifications are not independently verified by this audit.
2. Build deck-edit deltas from weekly snapshots of your own deck corpus to
   derive swap pairs without any external scrape.
3. Run the 60-query validation slice before adopting any amber source.
4. Request licences for EDHREC and Archidekt, then Moxfield, in that order.
5. Trial Yugipedia Card Tips for Yu-Gi-Oh synergy, which co-occurrence misses.
