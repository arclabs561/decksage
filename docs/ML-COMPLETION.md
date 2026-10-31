# What completes the ML

Ordered by dependency, not ambition. Each item states what is true today, what
has to exist for it to be finished, and how we know. "Complete" here means the
claim can be made honestly, not that the model is good.

Status snapshot: 2026-10-29. Evidence: `scripts/maintenance/verify_artifacts.py`,
`src/ml/evaluation/label_gate.py`, `.agents/reports/2026-10-28-*`.

## 1. Make the evaluation sets canonical — DONE 2026-10-29

**Done:** the gate-passing sets are now the canonical ones. 162 Magic, 197
Pokemon and 263 Yu-Gi-Oh structurally contradictory judgments were removed; the
originals are byte-identical in `data-local/test-set-archive-20261029/` and both
hashes are in `data/test_sets/REPAIR-LEDGER.json`. All three pass
`gate_or_refuse`, and the evaluator loader and the gate agree on eligibility
counts. Canonical hashes: magic `229e9f82…3240`, pokemon `c8b6de95…7e24`,
yugioh `3ab0b575…00aa`.

**Two gaps remain, deliberately not papered over:** `data/test_sets/` is
gitignored, so the ledger is written beside the sets but not versioned; and
nothing refuses the archived files by hash yet. Both matter only if someone
reintroduces the old files.

## 2. One representation surface (blocks honest comparison)

**Today:** `verify_artifacts.py` exits 0, but two artefacts are `HISTORICAL`
(fusion weights, legacy text `.npy`) and the text encoder identity is only now
recorded. `fusion.py` reads a layout nothing writes; `hybrid_search.py` writes a
different one; both are 768-D and used to disagree on 41% of top-10 neighbours.

**To finish:** resolve every served representation through one manifest lookup —
`(game, capability, task) -> {path, hash, dim, encoder, loader}`, with explicit
refusal codes. Retire the legacy `.npy` read path once fusion loads the
encoder-keyed cache.

**Done when:** no module computes its own cache path, and a dimensional or
encoder mismatch is a startup refusal rather than a silent degrade.

## 3. Restore the missing signal — DONE 2026-10-29 (unweighted)

**Done:** `scripts/data_processing/build_archetype_signal.py` builds
`experiments/signals/<game>/archetype_{staples,cooccurrence}.json` from the deck
archetype labels the repo ships, with a per-game manifest and SHA-256. Startup now
reads `signals: 3/3 loaded … Missing=none`, after mounting
`./experiments/signals` read-only into the dev container — the artefacts live
outside `data/`, which is why a restart alone still said 2/3.

**Caveat that keeps this honest:** the signal is loaded but **weight 0.0** until
item 4 calibrates it, and the startup line says `Unweighted=archetype`. Coverage
is sparse and uneven: 716 of 36,453 Magic cards, 464 Pokemon, 2,619 Yu-Gi-Oh. A
loaded signal that carries no weight changes no ranking.

## 4. Recalibrate fusion — RUN, published, and it collapses to embedding

**Done 2026-10-29.** Experiment 0067 (pre-registered, then completed) calibrated on
the canonical set with partial coverage: 27 grid points, 2,437 fit / 610 holdout
queries, **holdout nDCG@10 0.5088 at 89.7% coverage**. Weights are served from
`data/embeddings/fusion_weights_magic.json`, and the loader refuses any file that
does not carry its objective, coverage and experiment id.

**What the numbers say.** The optimum is `embed=1.0`, everything else `0.0`. On
these labels fusion *is* embedding similarity: jaccard and text survived no grid
point, and functional/visual were never computable in that script. That contradicts
the substitution preset, which zeroes co-occurrence on the claim that it
anti-correlates substitutes — the preset is now bypassed when calibrated weights
are served, and a preset that zeroes every supplied weight falls back to those
weights instead of producing a 500.

**Two things this leaves open.** RRF returns rank-based scores (~0.016), so the
UI's percentage is not a similarity magnitude; and Magic is the only recalibrated
game. Both are recorded, not hidden.

## 5. Decide the reranker

**Today:** the served linear reranker is retired by default; its producer raises
and its labels were withdrawn. Nothing replaces it, so `/v1/similar` runs on
primary embeddings.

**Decided 2026-10-29: retired, not deleted.** The code path stays behind
`DECKSAGE_ENABLE_LINEAR_RERANKER` (default off), and each `*_reranker_run.json` is
now recorded in `data/embeddings/PROVENANCE.json` with `status: historical` and
the reason. Deleting the path today would remove the only artefact that documents
what the old default did, and there is nothing to replace it with until item 4
produces calibrated weights.

**Done when:** either a replacement reranker is served with declared member
hashes, or the artefacts are archived out of `data/` at the next cleanup. Until
then the retirement is a recorded decision, not an omission.

## 6. Deck building consumes representations, not just embeddings

**Harness delivered 2026-10-29:** `scripts/evaluation/compare_recommendations.py`
holds the candidate set, judged pairs and retrieval depth fixed, asserts that both
arms scored an identical tuple, and reports a paired-bootstrap CI with a
30-query floor and a four-value verdict. It refuses to run on a set the gate
blocks. It measures re-scoring of the baseline's shortlist, not full retrieval —
that is its documented limit.

**First measurement on canonical labels (2026-10-29).** Magic, task `substitute`,
depth 50 shared candidate set, 1333 usable queries: baseline `magic_v7_spectral_mu35`
nDCG@10 **0.5228**, candidate adding `magic_v7_fused` **0.5094**, paired 95% CI for
the delta **[-0.0179, -0.0090]**. Verdict: `candidate_worse` — adding the fused
source degrades re-scoring of the same shortlist. Result file:
`data/results/compare_magic_substitute_20261029.json`.

This does not say the fused embedding is bad in general; it says that, on these
judged pairs and this shortlist, it does not help, and the interval is tight
enough to rule out a small gain. Any claim that it improves recommendations now
needs a different regime (full retrieval, another task, or a different
combination) to be made at all.

**Correction 2026-10-31 — the harness was scoring coverage, not re-scoring.**
The Magic test set annotates a median of 11 candidates per query while the fixed
pool is the top-50, and nDCG counted the other 39 as irrelevant. Every arm that
promoted a card from ranks 12-50 lost by construction: the 0072 tag delta was
-0.121 where >=20 candidates were judged and -0.219 where <20 (Spearman +0.23);
0074 was -0.212 versus -0.490. The harness now refuses a sparse pool
(`Coverage.check`, typed in `src/ml/contracts/evaluation.py`) and supports
`--judged-only`.

On judged pools the picture inverts: tag Jaccard is **+0.0787 nDCG**
(CI [+0.0684, +0.0905]) over the embedding, and the reprint boost is +0.0033
overall but **+0.2421** on the 35 queries where a reprint is in the pool
(0076-0079). The test set itself also carries label noise: a stratified 60-pair
re-judge shows MAE 0.194 and a high band inflated from 0.80 to 0.56
(`data/results/label_noise.json`). Do not treat the 2026-10-29 fused-embedding
negative as final until it is re-run judged-only.

**0080 (2026-10-31) — text is the signal, the fusion is not.** A supervised
pair ranker over E5 text, tags, co-occurrence and card attributes scores
**0.5680** nDCG@10 on 2,550 judged-pool queries against tag Jaccard **0.5519**
(delta +0.0160, CI [+0.0108, +0.0216]) and the co-occurrence embedding
**0.5006**. E5 text cosine alone scores **0.5686**, so the supervised fusion adds
nothing over the text representation. The learned gain is real but belongs to
text; the next step is a cross-encoder or contrastive fine-tune, not more
features. Label noise (MAE 0.194 vs fresh judges) still bounds the measurement.

**0081 (2026-10-31) — the candidate ceiling is text, not the graph.** With the
E5 cache extended from 25,892 to 37,214 cards, text retrieval finds a functional
reprint at **0.971 recall@10 / 1.0 @50**, against **0.319 / 0.507** for
`magic_v7_spectral_mu35` on the same 69 queries. Reprints share oracle text, so
this is a text-identity win and does not transfer automatically to differently
worded substitutes. It does settle where the candidate pool should come from:
text retrieval, then the judged functional signal as a re-ranker.
`/v1/index/status` now reports per-game catalog, Meilisearch and Qdrant coverage
(Magic Qdrant is 71% by construction; Meilisearch is 100%).

**0082 (2026-10-31) — text is also the functional-positive retriever.** On 272
refined queries and 278 positives (median judge score >= 0.5), E5 reaches
**0.721 recall@10 / 0.904 @50** against **0.149 / 0.313** for the co-occurrence
graph (delta +0.592, CI [+0.531, +0.660]). The refined pairs were sampled from
several sources, so this is not the graph's own neighbourhood. The graph does
not belong in the substitute candidate pool; text retrieves, the judged
functional signal re-ranks. Caveat: 278 LLM-labelled positives, some exact
reprints.

**Today:** completion uses primary embeddings and the co-occurrence graph. It
does not consult fusion weights, the text index or a trained re-ranker, so
"learned representations improve recommendations" is untested for the surface
where it would matter most.

**To finish:** route completion's scoring through the same capability lookup as
item 2, then run a pre-registered comparison: identical candidate sets, identical
judged pairs, retrieval depth fixed, one variable changed.

**Done when:** the comparison is recorded and either supports the claim or
retires it.

## 7. Simulation, as an instrument (parallel track)

**Today:** Pokémon `cabt` runs (114 games/s, mirror-match degeneracy detected and
reported as `partial`); Magic waits on a Forge jar; Yu-Gi-Oh! waits on a licence
decision. `docs/adr/0004-*` sets Gate A before any optimisation claim.

**Gate A result, 2026-10-29: FAILED at the first check.** `scripts/simulation/gate_a.py`
ran the Pokémon engine twice on the same deck pair and the same seed schedule and
got *different* per-game outcome vectors (8 games each, 3 wins / 0 losses / 5 draws
in the first). The engine's `battle_start` is not reproducible from our side, so
no comparison built on it can be trusted — the instrument fails before it measures
anything. Magic and Yu-Gi-Oh! correctly return `NOT_PROVEN` with their reasons.

**To finish:** find why the engine is non-deterministic (unseeded RNG inside
`libcg`, or process-global state) and make the seed schedule real, or accept that
win rates from this engine are unusable and stop there — which is a legitimate
outcome for item 7.

**Done when:** a deck ranking is reproducible from a seed schedule and the
coverage list, and the ADR's refusal list is still respected.

## Not on this list

More embeddings, more models, a bigger index. The audits found the interface and
the labels to be the limiting factors, not model capacity. Adding a model before
items 1-3 would produce a better-looking number measured on the same broken
denominator — the failure that withdrew 0065 and 0066.
