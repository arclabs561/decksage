# ADR-0004: simulation is an instrument before it is an optimiser

**Status**: proposed
**Date**: 2026-10-28

## Context

The owner asked for two capabilities: simulate games so that decks can be
optimised against something other than a heuristic, and generate initial deck
ideas from natural language. The user-visible outcome for the first is one
sentence that DeckSage cannot say today: "of these two decks, this one is
stronger, and here is the evidence and its scope." Everything the repository
currently says is about cards and shapes -- substitute and synergy ranking,
completion by greedy, beam or optimal transport, and a deck score built from
mana-curve distance and functional-tag coverage
(`src/ml/deck_building/deck_quality.py`). No code in the repository simulates a
game. Win rates exist only where round results are supplied:
`matchup_analysis.py` is exercised by tests alone, and the win-rate graph
integration reads a `metadata.placement` field that the deck corpus does not
have.

The obvious source of outcome labels is also absent. Some scraped decks carry
`placement` from event standings -- MTGO Challenge and League results, MTGTOP8
and Limitless cuts -- but the scraped slice is the top of each event, and no
deck file carries a per-match field: no win, loss, round or record key appears
anywhere in `data/decks/`. A top-cut placement is a selected observation, not a
win rate, so no local number can serve as the reference standard this decision
needs. `config/label_sources.toml` has no outcome class and no source supplying
match results.

## Decision

- Simulation enters this project as a **measuring instrument with a named
  scope**: one game, two decks, a fixed seed schedule, a fixed opponent field,
  and an explicit card-effect coverage report. It is not a rules engine and is
  never described as one.
- No search, no optimisation claim and no user-facing win-rate surface is
  authorised until Gate A below passes on a frozen external reference set.
- The instrument is judged by agreement with real outcomes, not by internal
  consistency, plausibility or coverage of card text.
- Simulation outcomes form a new task label space, `outcome`, under ADR-0001.
  They are not derived from, and do not extend, the `substitute`, `synergy`,
  `meta` or `completion` spaces.
- Natural-language deck ideas are decided separately and are not gated on
  simulation. Their design is in
  `.agents/reports/2026-10-28-nl-deck-ideas-design.md`.

## Non-goals

- Not a rules-accurate tournament simulator. Stack, priority, replacement
  effects, layers and complete card text are out of scope; unimplemented cards
  are refused, not approximated.
- Not a card-price optimiser. Budget is a constraint passed through to
  completion, never an objective.
- Not a replacement for similarity search. Substitute and synergy ranking keep
  their own label spaces and their own evaluators.
- Not a source of training data or test labels.

## Options

**Do nothing: keep similarity plus completion heuristics and never claim a
win-rate gain.** Cost: zero. Proves: nothing about performance, which is the
point -- curve distance and tag coverage are validated as descriptions of a
deck, not as predictors of its results, and no local evidence connects either to
outcomes. Breaks when a user asks which of two decks is better and the honest
answer is "unknown"; that answer is currently correct.

**Borrow a rules-complete engine (Forge, XMage, SabberStone class).** Cost:
integration plus pilot work per game. Throughput is not one number: Forge plays
Commander at roughly 25-43 s per game on other people's hardware, while the
Pokemon `cabt` engine was measured here at 36-47 games per second with trivial
policies (`.agents/reports/2026-10-28-simulation-engines-research.md` §5,
`.agents/reports/2026-10-28-deck-optimisation-methods.md` §3.3). A six-hour run
on a slow engine buys a few hundred games, about ±3-4 points on one deck; on
`cabt` it buys millions. A 2-point question still needs thousands of paired
games whichever engine is chosen. Proves: the most faithful available proxy for real play. Breaks
on throughput first, on card coverage for Pokemon and Yu-Gi-Oh second, and on
pilot confounding third -- a deck tuned against a weak pilot is not a deck tuned
for a human.

**Deliberately lossy simulator, validated against outcomes (recommended).**
Cost: a card-effect table for one format's relevant card pool plus a turn model,
measured in weeks, not days. Proves: differences that come from curve, role
density, redundancy, answer count and mana consistency, inside its declared
coverage. Breaks at every interaction-dependent card and at every deck outside
the coverage list; its ranking is only as good as the effects it implements.

**Outcome surrogate regression without simulation.** Cost: days, and it needs
an external corpus of decks with real results. Proves: an out-of-sample
correlation between deck features and results, which is a weaker and cheaper
claim than a counterfactual. Breaks on the data: a newly generated deck has no
outcome, so a surrogate cannot rank candidates that do not exist yet, and
card-level win rates are confounded by deck strength and by not being drawn.

**Recommendation: the lossy simulator, and only as far as Gate A.** The
deciding factor is not engine fidelity and not search cleverness; it is whether
the measuring instrument is valid, because every method in the literature
competes for the same scarce resource -- validated games per deck -- and a
borrowed rules engine spends that resource between 22 ms and 43 s per game
depending on the engine and format. A lossy simulator
buys the games; the gate then decides whether they mean anything. What breaks
this: if the reference set cannot be licensed, no option survives, and the
honest answer reverts to do nothing. This flips to the borrowed engine if a
sponsored or cloud budget removes the throughput constraint, and to do nothing
if Phase B shows the existing surrogate already predicts the reference ordering.

## Gate A

Required before Phase D is authorised, before any optimisation claim, and before
any user-facing wording that implies a win rate. Each item is cheap and can
fail.

1. **Determinism.** Rerunning a comparison on the same seed schedule returns the
   identical per-game result vector, not merely the same rate.
2. **Positive control.** A known-tier deck beats a uniform-random legal deck by
   at least 20 points at n=200 paired games, where the worst-case interval
   half-width at that n is about 7 points. The failure this catches is
   documented: a 2016 dissertation's random baseline decks averaged 71.7%
   because the opponent was too weak.
3. **Coverage floor.** Every card in both decks has an implemented effect. A
   comparison containing an unimplemented card is refused, not scored with that
   card treated as vanilla. Defaulting silently is the Weakstone/Mightstone
   error from experiment 0066 in a new place: the card table is the label
   construction.
4. **External agreement.** On a frozen reference set of decks with real results,
   the simulator's ordering agrees with the real ordering at Spearman >= 0.6
   with a bootstrap interval excluding zero, and exceeds the incumbent
   curve-and-tag surrogate's agreement on the same decks by a pre-declared
   margin. If it does not, the simulator adds nothing beyond the surrogate and
   the programme stops.
5. **Matched denominators.** Both arms play the same opponent list and seed
   schedule, and the discordance rate is reported alongside paired n. Two arms
   measured on different opponents is the 0066 error; a nominal game count
   without the opponent count is the same error at the reporting layer.

## What a result licenses

A simulation result licenses exactly one sentence, with every qualifier
attached: on instrument version `S`, pilot `P`, seed schedule `E`, opponent
field `F` (with its fingerprint), data snapshot `D`, deck A beat deck B in `W`
of `N` paired games, difference `d` with a 95% interval, at coverage `c`. It
also licenses internal search decisions -- which candidate to promote -- because
a promotion is not a claim.

It does not license: an absolute win rate against humans; "this deck wins X%";
a judgement that a card is good; transfer to another field, format, snapshot or
pilot; comparison of decks outside coverage; any substitute, synergy or meta
claim, which stay with the judge-labelled task spaces and with the ranking-only
limit that public paraphrase agreement allows (`docs/JUDGE-CALIBRATION.md`); any
statement about the served ranker, since `eval_per_mode.py` measures raw cosine
while the API serves a reranker; and any entry into `data/test_sets/`, training
data or the annotation corpus. It also does not rehabilitate experiments 0065 or
0066, whose numbers stay withdrawn.

The structural gate applies unchanged in shape: `src/ml/evaluation/label_gate.py`
refuses to score labels that contradict themselves rather than scoring them with
a warning. A comparison whose arms differ in opponent list, seed schedule or
coverage is refused the same way.

## Rejected

- Reporting a simulated percentage to users as a deck's strength. The number is
  reproducible without being valid, which is precisely the failure shape of
  0065: a metric that was measured, stored and treated as a result while three
  of its five inputs were silently dead.
- Treating simulation as ground truth for training or for the test sets. It is
  generated by our own code, so agreement with it measures our assumptions.
- Having a language model emit the final card list. Unresolvable names and
  invented cards are the predictable failure, and the deck would arrive with no
  provenance beyond a prompt.
- Optimising on the same opponent field that produced the fitness. Thousands of
  candidates against one fixed benchmark turns search into a multiplicity
  problem: with twenty comparisons at a 0.05 threshold the chance of at least one
  spurious winner is 1 - 0.95^20, about 64%, so a result needs a fresh, locked
  gauntlet to mean anything.
- Building the search layer first because it is the visible deliverable.

## Consequences

- The cheapest outcome is a documented "no", reached in about a day by Phase B
  rather than after a month of engine work.
- A passing Gate A produces a claim narrower than the request: one game, one
  field, one pilot, an interval and a coverage number. Users will read the
  percentage and skip the qualifiers, so the wording must carry the scope, not a
  footnote.
- The reference set becomes a governed asset: it needs a licence verdict in the
  registry before use, a fingerprint, and a freeze date, exactly like a test set.
- Card-set rotation and bans invalidate a field. Every simulation artefact must
  name a snapshot, and a stale snapshot is a stale claim.
- The lossy instrument will disagree with a real engine on interaction-heavy
  decks. That disagreement is information about coverage, not a bug to tune
  away.

## Phases

Effort is a rough range for one workstation, not a schedule.

| Phase | Artefact | Effort |
| --- | --- | --- |
| A. Reference set | Frozen deck-plus-result set for one game, with licence verdict, provenance and fingerprint | 2-3 days |
| B. Incumbent baseline | Out-of-sample rank agreement of the existing curve-and-tag surrogate against the reference set: the cheap falsifier | 1 day |
| C. Instrument v0 | One-game, two-deck, seed-deterministic simulator with a card-coverage report and a replay script | 2-4 weeks |
| D. Gate A | Experiment record with determinism, positive control, coverage, external agreement and discordance | 2-3 days of runs |
| E. Search | Swap-neighbourhood search pruned by the surrogate, successive halving on paired games, confirmation on a locked field | 1-2 weeks |
| F. Product surface | A comparison view that shows the scope block and refuses to print an unqualified number | 1 week |

Phase B is the smallest prototype that could falsify the whole idea, and it is
placed before any simulator work deliberately: if the incumbent surrogate
already predicts the reference ordering, simulation is unnecessary; if no
reference set can be licensed, the programme is blocked at the data rather than
at the engine. A falsifier that runs after the build is not cheap.

## Open questions

- Which outcome source is usable, under what terms, and does it license
  redistribution of derived numbers? Settled by a registry entry with a verdict
  and the date on which the terms were read (ADR-0003).
- Is the target claim "which of two decks is better" or "find a better deck"? A
  pairwise claim needs hundreds of paired games; a search claim needs thousands
  and a locked field. Settled by the owner naming the sentence they want to be
  able to say.
- Which game is the pilot? Magic has the deepest card pool and the most card
  text to implement; Pokemon has simpler state and a template corpus; Yu-Gi-Oh
  has the least local template support. Settled by a coverage estimate over the
  top cards of each format, not by preference.
- Does a pilot matter more than fidelity? Settled by running the same deck set
  through two policies at equal fidelity and comparing the orderings.
- Is one point of win rate worth any of this? A 2-point question costs thousands
  of paired games, which at measured rules-engine throughput is hundreds of
  hours, so the honest target is a coarse ordering. Settled by the owner
  accepting or rejecting that ceiling before Phase C.

## See also

`.agents/reports/2026-10-28-deck-optimisation-methods.md` for the method survey,
sample-size arithmetic and prior-art failures this record relies on.
`.agents/reports/2026-10-27-evaluation-integrity.md` for the withdrawn results
and the audit standard applied here. The simulation-engines research report was
not present in `.agents/reports/` when this ADR was written, so engine-specific
claims are sourced only from the methods report.
