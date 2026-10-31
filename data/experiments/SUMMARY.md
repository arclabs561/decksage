# Experiment Summary

Chronological log of all ML/DS experiments. Each row links to a detailed YAML file.

## Experiments

| ID | Date | Title | Game | Data | Key Metric | Result | File |
|----|------|-------|------|------|------------|--------|------|
| 0001 | 2026-03-17 | v4 co-occurrence baseline | all | M:7.1M P:16.7K Y:1.8M pairs | overall nDCG | M:0.151 P:0.049 Y:0.554 | [0001](0001_v4_baseline.yaml) |
| 0002 | 2026-03-17 | v5 fused (enriched + ns=-0.5 + attr) | all | M:7.1M P:16.7K Y:1.8M pairs + attributes | overall nDCG | M:0.156 P:0.247 Y:0.554 | [0002](0002_v5_fused.yaml) |
| 0003 | 2026-03-18 | Pokemon pairs expansion 16K->179K | pokemon | 179,914 pairs (from 16,676) | overall nDCG | 0.294 (+19% rel, plateau) | [0003](0003_pokemon_expanded_pairs.yaml) |
| 0004 | 2026-03-19 | LightGCN hyperparameter sweep | magic | 331,264 edges, 15,697 nodes; 500 queries | overall nDCG | sweep: 0.545 (inflated), canonical: 0.095 (WORSE than v5 0.154) | [invalid] [0004](0004_lightgcn_sweep.yaml) |
| 0005 | 2026-03-19 | E5 multi-task fine-tuning | magic | 8,084 samples (3,084 pairs + 5,000 edges) | train loss | 0.027 (converged) | [0005](0005_e5_multitask_finetune.yaml) |
| 0006 | 2026-03-19 | Flow-based deck completion | magic | 4,500 train / 500 test decks | hit@10 | 0.031 (first pass) | [0006](0006_flow_completion.yaml) |
| 0007 | 2026-03-19 | Fusion weight switching fix | all | v2 test sets, substitution pairs sub>0.5 | recall@10 | M:0.38 P:0.38 Y:0.62 | [0007](0007_fusion_weight_fix.yaml) |
| 0008 | 2026-03-17 | Annotation v2 test sets | all | 250/198/140 queries (M/P/Y) | annotated pairs | M:481 P:300 Y:300 | [0008](0008_annotation_v2_test_sets.yaml) |
| 0009 | 2026-03-17 | Card context in annotations | all | card attributes CSV (oracle text) | error rate | 16% -> 1% | [0009](0009_annotation_card_context.yaml) |
| 0010 | 2026-03-18 | Annotation enrichment | all | 6,690 pairs | enriched pairs | 6,690 total | [0010](0010_annotation_enrichment.yaml) |
| 0011 | 2026-03-17 | OT completion v2 | all | OT completion module (no new data) | -- | reformulated (was degenerate) | [0011](0011_ot_completion_v2.yaml) |
| 0012 | 2026-03-17 | LightGCN reconstruction loss | all | M:7.1M Y:1.8M edges | -- | BPR collapses, recon works; quality pairs not recorded **[incomplete]** | [0012](0012_lightgcn_reconstruction_loss.yaml) |
| 0013 | 2026-03-18 | Per-mode eval framework | all | v2 test sets + 14 search queries | -- | eval scripts created | [0013](0013_per_mode_eval.yaml) |
| 0014 | 2026-03-18 | IAA model rotation | all | 4-model judge pool | models | 4-model pool | [0014](0014_iaa_model_rotation.yaml) |
| 0015 | 2026-03-18 | Diverse pair generation | all | 1,600 pairs (600/501/499) | pairs | 1,600 (4 sources) | [0015](0015_diverse_pair_generation.yaml) |
| 0016 | 2026-03-18 | Annotation edges export | all | enriched v2 test sets | edges | 3,232 exported | [0016](0016_annotation_edges_export.yaml) |
| 0017 | 2026-03-19 | E5 fine-tuned eval | magic | 500 queries, 3,290 annotations | nDCG | within-annotation ranking | [invalid] [0017](0017_e5_finetuned_eval.yaml) |
| 0018 | 2026-03-19 | LightGCN canonical eval | magic | 15,697 (LightGCN) vs 21,151 (v5) cards | nDCG | 0.095 (inflated sweep: 0.545) | [0018](0018_lightgcn_canonical_eval.yaml) |
| 0019 | 2026-03-19 | Eval metrics audit | all | literature review (no dataset) | -- | recommendations | [0019](0019_metrics_audit.yaml) |
| 0020 | 2026-03-19 | Coverage fix via text embeddings | magic | v5_fused + e5-base-v2 + card catalog | coverage | 11.6% -> 29% | [0020](0020_catalog_coverage_fix.yaml) |
| 0021 | 2026-03-19 | Stratified nDCG bias check | magic | 500 queries (329 annotated) | bias ratio | popular/niche split | [0021](0021_stratified_ndcg.yaml) |
| 0022 | 2026-03-19 | Set/keyword/precon edges | magic | 36,923 cards, 492 sets | edges | new edge types added | [0022](0022_set_edges.yaml) |
| 0023 | 2026-03-19 | v7 retrain w/ set edges | magic | 4.31M edges (6 types) | nDCG | coverage up, nDCG down | [0023](0023_v7_set_edges_retrain.yaml) |
| 0024 | 2026-03-19 | LightGCN collapse root cause | all | LightGCN vs v5, 331K edges (0.27% density) | -- | trivial solution on sparse graphs | [0024](0024_lightgcn_collapse_diagnosis.yaml) |
| 0025 | 2026-03-19 | Ceiling analysis | magic | 836 eval queries | ranking | 95.6% optimal, retrieval is bottleneck | [0025](0025_ceiling_analysis.yaml) |
| 0026 | 2026-03-20 | All-games baseline post-fixes | all | 836/639/689 queries (M/P/Y) | nDCG | M:0.113 P:0.110 Y:0.282 | [0026](0026_all_games_baseline_with_fixes.yaml) |
| 0027 | 2026-03-20 | IAA Krippendorff alpha | magic | 100 pairs, 4 judges, 373 ratings | alpha | 0.43 (judges disagree) | [0027](0027_iaa_krippendorff.yaml) |
| 0028 | 2026-03-20 | Archidekt Commander scrape | magic | 507 decks, 1.59M pairs | pairs | 1.59M from 507 decks | [0028](0028_archidekt_commander_scrape.yaml) |
| 0029 | 2026-03-20 | v8 Commander retrain | magic | 1.92M pairs (331K + 1.59M), 507 decks | nDCG | coverage up, nDCG down | [0029](0029_v8_commander_retrain.yaml) |
| 0030 | 2026-03-20 | MetaPath2Vec first pass | magic | 3 edge types: 331K+1.46M+927 | sub nDCG | 0.114 (5ep baseline) | [0030](0030_metapath2vec_first_pass.yaml) |
| 0031 | 2026-03-20 | MetaPath2Vec v2 beats v5 | magic | 3 edge types: 331K+1.46M+927 | sub nDCG | 0.177 (+43% over v5) | [invalid] [0031](0031_metapath2vec_v2_beats_v5.yaml) |
| 0032 | 2026-03-20 | Dual-embedding fusion analysis | magic | 3,819 GT cards, v5 + MP2V | nDCG | v5+MP2V = +16% | [invalid] [0032](0032_fusion_analysis.yaml) |
| 0033 | 2026-03-20 | Data curation audit | magic | 83,611 decks, 15,697 cards | -- | dedup, land noise, gaps | [0033](0033_data_curation_audit.yaml) |
| 0034 | 2026-03-20 | rankops CombMNZ vs RRF | magic | 200 queries, top-50 per embedding | nDCG | CombMNZ +10% over RRF | [invalid] [0034](0034_rankops_fusion_comparison.yaml) |
| 0035 | 2026-03-20 | Commander data scaling | magic | 3.8M pairs from 2,615 decks | pairs | 3.8M from 2,615 decks | [0035](0035_commander_data_scaling.yaml) |
| 0036 | 2026-03-20 | MetaPath2Vec tuning | magic | MP2V + 9 attributes, PCA 128D | sub nDCG | attr fusion hurts; 40ep variant not recorded **[incomplete]** | [0036](0036_metapath2vec_tuning.yaml) |
| 0037 | 2026-03-20 | MetaPath2Vec 40ep | magic | 35,265 cards (vocab) | sub nDCG | 0.186 (+50% over v5) | [invalid] [0037](0037_metapath2vec_40epochs.yaml) |
| 0038 | 2026-03-20 | MetaPath2Vec 80ep | magic | Magic graph walks (count not recorded) | sub nDCG | 0.198 (+60% over v5) | [invalid] [0038](0038_metapath2vec_80epochs.yaml) |
| 0039 | 2026-03-21 | MetaPath2Vec 160ep | magic | 35K cards, 29M edges | sub nDCG | 0.228 (LEAKED) | [invalid] [0039](0039_metapath2vec_160epochs.yaml) |
| 0040 | 2026-03-21 | Box containment POC (deck-contains-card) | magic | 2,001 decks, 127,994 triples | AUC | 0.504 (no separation, degenerate) | [0040](0040_box_containment_poc.yaml) |
| 0041 | 2026-03-21 | Epoch sweep (leak fix) | all | 4-35K cards, no ann edges | sub nDCG | poke:0.096 yug:0.311 (160ep) | [invalid] [0041](0041_epoch_sweep_leak_fix.yaml) |
| 0042 | 2026-03-21 | Cleora iteration sweep | all | 4-35K cards, 500K-29M edges | sub nDCG | M:0.103 P:0.103 Y:0.284 | [invalid] [0042](0042_cleora_iteration_sweep.yaml) |
| 0043 | 2026-03-21 | Cone containment (cones > boxes) | magic | 116 train triples, 282 cards | AUC | 0.700 (vs box 0.500) | [invalid] [0043](0043_cone_containment.yaml) |
| 0044 | 2026-03-21 | Cone + transitive closure | all | 145-344 upgrade pairs + TC | AUC | M:0.762 P:0.547 Y:0.649 | [0044](0044_cone_transitive_closure.yaml) |
| 0045 | 2026-03-21 | Cone + TC + hard negatives | all | 146-398 pairs + hard negs | AUC | M:0.857 P:0.603 Y:0.553 | [invalid] [0045](0045_cone_tc_hardneg.yaml) |
| 0046 | 2026-03-22 | MetaPath2Vec selective (deck+enriched+keyword) | all | 331K+1.46M+83K edges (Magic) | sub nDCG | selective run never evaluated **[incomplete]** | [0046](0046_metapath2vec_selective.yaml) |
| 0047 | 2026-03-22 | v6 blended: PecanPy + oracle text edges | all | merged + oracle_text + game edges | sub nDCG | no blend nDCG measured **[incomplete]** | [0047](0047_v6_blended_oracle_text.yaml) |
| 0048 | 2026-03-21 | MetaPath2Vec v2: 8 edge types | magic | 35K cards, 12M edges (8 types) | sub nDCG | 0.114 INFLATED (Commander dilutes signal, regressed from 0.228) | [0048](0048_metapath2vec_v2_expanded_edges.yaml) |
| 0049 | 2026-03-21 | Card containment (box embeddings) | all | M:168 P:292 Y:263 train triples | AUC | M:0.500 P:0.583 Y:0.500 (degenerate, too sparse) | [invalid] [0049](0049_card_containment.yaml) |
| 0050 | 2026-03-22 | Expanded Commander Cleora (51K decks) | magic | 25.2M Commander edges | sub nDCG | 0.100 (unchanged from 18K decks, Commander != cross-format sub) | [0050](0050_expanded_commander_cleora.yaml) |
| 0051 | 2026-03-22 | Magic epoch sweep (no leakage) | magic | 35K cards, self-supervised only | sub nDCG | 0.127 INFLATED at 80ep (best Magic pre-dedup, +27% over Cleora) | [invalid] [0051](0051_magic_epoch_sweep.yaml) |
| 0052 | 2026-03-22 | Annotation dedup correction | all | deduped test sets | sub nDCG | Selected nDCG comparisons: 84/78/101% higher before dedup; snapshot provenance incomplete | [0052](0052_dedup_correction.yaml) |
| 0053 | 2026-03-23 | **Training variance ablation** (key) | magic | v7 vs v8 edgelist, 3 seeds each | sub nDCG | v7 mean 0.094 (std 0.001), v8 mean 0.090. Deployed v7 (0.102) was 2.5-sigma outlier | [0053](0053_training_variance_ablation.yaml) |
| 0054 | 2026-03-23 | **HGT mini-batch on A10G** (key) | magic | 12M edges, 36K nodes, 6 edge types | sub nDCG | 0.003 raw, 0.014 fused (link prediction AUC 0.80 but embeddings not similarity-preserving) | [0054](0054_hgt_mini_batch.yaml) |
| 0055 | 2026-03-24 | HGT contrastive (InfoNCE) on A10G | magic | same as 0054 | sub nDCG | 0.002 raw, 0.012 fused (worse than link pred 0.014; loss plateaued epoch 20) | [0055](0055_hgt_contrastive.yaml) |
| 0056 | 2026-03-24 | Residual PPMI (SVD) + degree debiasing | magic | v7 edgelist | sub nDCG | PPMI 0.084, v7_debiased 0.103, spectral_debiased 0.107, spectral 0.107 | [0056](0056_residual_ppmi_and_debiasing.yaml) |
| 0057 | 2026-03-25 | **Multi-model cascade annotation** (key) | all | Groq 70B + Cerebras 235B cascade | corr vs IAA | **0.639 calibrated** (vs $2-15 IAA at $0.40/1K). Cleanup of 3,349 bad annotations: Magic nDCG +21.6% | [0057](0057_multi_model_cascade_annotation.yaml) |
| 0058 | 2026-03-25 | **Fill eval holes round 1** (key) | all | 5K holes per game, multi cascade | sub nDCG | Magic 0.104->**0.233**, Pokemon 0.088->**0.190**, YuGiOh 0.160->**0.240**. ~$6 total. 42K holes remain | [0058](0058_fill_eval_holes_round1.yaml) |
| 0059 | 2026-03-25 | **Fill eval holes round 2 -- SATURATED** (key) | all | remaining holes, multi cascade | sub nDCG | Magic **0.525**, Pokemon **0.437**, YuGiOh **0.478**. All saturated (gap<0.005). ~$23 total. 89K annotations | [0059](0059_fill_eval_holes_round2.yaml) |
| 0060 | 2026-03-26 | Fusion-path substitute eval | magic | v7_spectral, 36K annotations | sub nDCG | Cosine: **0.525**, Fusion: **0.031** (gap=0.256). Test set is cosine-specific; fusion candidates unjudged. Need fusion-specific annotation filling | [0060](0060_fusion_path_eval.yaml) |
| 0061 | 2026-03-31 | Text_e5 annotation holes | all | 6K new annotations | sub nDCG | Co-occur nDCG drops 3-6% (expected: can't rank text-similar candidates) | [0061](0061_text_e5_annotation_holes.yaml) |
| 0062 | 2026-03-31 | Text_e5 vs co-occurrence quality | all | condensed sub nDCG | condensed nDCG | **CONTAMINATED**: E5 trained on the eval set; held-out quality unknown | [invalid] [0062](0062_text_e5_vs_cooccurrence_quality.yaml) |
| 0063 | 2026-03-31 | Cross-encoder reranker training | all | 100K annotation pairs | Pearson/nDCG | v2: Pearson **0.695** (inflated), v3: **~0.56** at epoch 0.9 **[incomplete]** | [invalid] [0063](0063_cross_encoder_reranker.yaml) |
| 0064 | 2026-03-31 | E5 bi-encoder fine-tuning | magic | 5,000 train / 2,079 val pairs | Pearson | 0.293 after 1 epoch (worse than 0.438 zero-shot; catastrophic forgetting) | [0064](0064_e5_finetuning.yaml) |
| 0065 | 2026-10-22 | Fusion calibration, dead-signal guarded | magic | v2 labels, seed-13 80/20 split; 3 of 5 signals live | holdout nDCG@10 | Withdrawn: invalid calibration objective | [invalid] [0065](0065_fusion_calibration_dead_signal_guard.yaml) |
| 0066 | 2026-10-26 | Reprint recall, judge-free | magic | 187 families / 396 cards from Scryfall oracle dump | historical capped hit score, mislabeled recall@10 | Withdrawn: false substitute labels and unmatched query sets | [invalid] [0066](0066_reprint_family_recall.yaml) |
| 0067 | 2026-10-29 | Fusion recalibration on canonical labels (magic) | magic | data/processed/pairs_large.csv | -- | ran 2026-10-29; mode partial-coverage (--allow-partial-coverage --min-coverage 0.5); grid_size 27; fit_queries 2437; holdout_queries 610; fit_ndcg_at_10 0.5036; holdout_ndcg_at_10 0.5088; holdout_coverage 0.8973; elapsed_seconds 1112; outcome published to data/embeddings/fusion_weights_magic.json with objective, coverage and experiment id; finding The grid's optimum sets every weight to zero except the co-occurrence embedding. In other words, on the canonical substitution labels, "fusion" reduces to embedding similarity: jaccard and text contributed nothing that survived the search, and functional/visual were never computed.; conflict That optimum contradicts the substitution task preset, which deliberately zeroes co-occurrence ("Co-occurrence anti-correlates substitutes") and leans on text/functional. Applying the preset on top of these weights produced an all-zero vector and a 500 at the fusion endpoint. The preset is now bypassed when calibrated weights are served, and WeightedLateFusion falls back to the supplied weights if a preset zeroes them. Recorded rather than silently averaged: one of the two is wrong for this data, and this run says the preset is wrong for these labels. | [0067](0067_fusion_recalibration_canonical.yaml) |
| 0068 | 2026-10-30 | Non-learned baselines for substitute scoring (magic) | magic | data/processed/card_attributes_magic_enriched.csv | -- | verdict candidate_better in both directions | [0068](0068_heuristic_baselines.yaml) |
| 0069 | 2026-10-30 | Logical composition over co-occurrence and embedding graphs (heyting) | magic | functional_score; unjudged = 0; IDCG from judged scores | -- | original_verdict not_supported; verdict inconclusive_measurement; measurement_caveat The constrained arms rank a shrunken subset of the embedding top-80; the Magic test set annotates a median of 11 candidates per query, so most constrained candidates are unjudged and scored 0. The unconstrained 1p arm is unaffected and stands. | [0069](0069_heyting_logical_composition.yaml) |
| 0070 | 2026-10-30 | tranz DistMult on the co-occurrence graph (magic) | magic | -- | -- | final_loss 5.7179; ndcg_at_10 0.072; verdict not_supported | [0070](0070_tranz_kge_cooccurrence.yaml) |
| 0071 | 2026-10-30 | External label anchor: Scryfall Oracle Tag overlap (magic) | magic | Scryfall Oracle Tags bulk, 2026-10-30T21:00:36Z | -- | verdict partial external support; note Oracle Tags are a card-level role/function proxy, not a pair-level substitution label. The score tracks shared roles but the correlation is well below the 0.30 support line; tag sparsity and coarse tags attenuate it. | [0071](0071_label_anchor_scryfall_tags.yaml) |
| 0072 | 2026-10-30 | Scryfall tag Jaccard as a substitute re-ranker (magic) | magic | Scryfall Oracle Tags bulk 2026-10-30T21:00:36Z | -- | baseline_ndcg_at_10 0.4942; tag_ndcg_at_10 0.3142; delta -0.1799; baseline_recall_at_10 0.6543; tag_recall_at_10 0.4989; recall_delta -0.1554; original_verdict candidate_worse; verdict inconclusive_measurement; measurement_caveat nDCG@10 counts unjudged candidates as 0. The tag arm promotes candidates outside the embedding neighbourhood, which the annotations mostly do not cover: delta is -0.121 where >=20 candidates are judged and -0.219 where <20 (Spearman +0.23). The tag prior is also weak (rho 0.20), so this arm is unmeasured rather than refuted. | [0072](0072_tag_jaccard_rerank.yaml) |
| 0073 | 2026-10-30 | Functional-reprint known-item probe (magic) | magic | data/raw/scryfall/oracle-cards.json | -- | embedding_queries 898; recall_at_10 0.3307; recall_at_50 0.5434; median_rank 37.0; judged_mean_functional_score 0.573; verdict weak known-item recall | [0073](0073_functional_reprint_probe.yaml) |
| 0074 | 2026-10-30 | Exact functional reprints as a fixed-candidate-set arm (magic) | magic | 483 | -- | usable_queries 1282; scored_queries 441; baseline_ndcg_at_10 0.5002; reprint_ndcg_at_10 0.1266; delta -0.3736; baseline_recall_at_10 0.6567; reprint_recall_at_10 0.1853; recall_delta -0.4714; original_verdict candidate_worse; verdict inconclusive_measurement; measurement_caveat The candidate pool is the embedding top-50 but only a median of 13 candidates per query are judged; delta is -0.212 where >=20 are judged and -0.490 where <20 (Spearman +0.47). Four identical reprints in the judged set are also labelled 0.0, so the strongest positives are partly mislabelled. The arm is unmeasured on this label set. | [0074](0074_reprint_rule.yaml) |
| 0075 | 2026-10-31 | Exact-reprint promotion inside the embedding's top-50 (magic) | magic | data/raw/scryfall/oracle-cards.json | -- | queries 2556; reprint_covered 35; baseline_ndcg_at_10 0.4978; boosted_ndcg_at_10 0.4972; delta -0.0006; covered_baseline_ndcg_at_10 0.6083; covered_boosted_ndcg_at_10 0.5617; covered_delta -0.0466; original_verdict candidate_worse; verdict inconclusive_measurement; measurement_caveat Of 43 reprint instances in the 35 covered queries, 17 are unjudged and therefore scored 0 (their baseline ranks are 11-46). Of the 26 judged instances, four identical reprints are labelled 0.0 and others 0.86-1.0. A 35-query subset with this label noise cannot decide the rule; the negative is a measurement artifact, not evidence about reprints. | [0075](0075_reprint_boost.yaml) |
| 0076 | 2026-10-31 | Judged-only re-test of the tag and reprint arms (magic) | magic | median 11 per query in the full pool; judged-only pool reported per query | -- | -- | [0076](0076_judged_only_retest.yaml) |
| 0077 | 2026-10-31 | Reprint boost on judged candidates only (magic) | magic | data/raw/scryfall/oracle-cards.json | -- | queries 2554; judged_pool_mean 11.52; reprint_covered 22; baseline_ndcg_at_10 0.5034; boosted_ndcg_at_10 0.5035; delta 0.0; covered_baseline_ndcg_at_10 0.6198; covered_boosted_ndcg_at_10 0.6228; covered_delta 0.003; baseline_recall_at_10 0.3362; boosted_recall_at_10 0.3362; recall_delta 0.0; verdict neutral | [0077](0077_reprint_boost_judged_only.yaml) |
| 0078 | 2026-10-31 | Reprint verdict after removing definitional label conflicts (magic) | magic | data/test_sets/annotated_magic_v2.json | -- | queries 906; excluded_pairs 14; baseline_ndcg_at_10 0.5355; candidate_ndcg_at_10 0.5216; delta -0.014; recall_delta 0.0503; verdict no_difference | [0078](0078_reprint_conflict_exclusion.yaml) |
| 0079 | 2026-10-31 | Reprint arms with the 31 missing/mislabelled pairs restored (magic) | magic | data/test_sets/annotated_magic_v2.json | -- | -- | [0079](0079_reprint_restored_labels.yaml) |
| 0080 | 2026-10-31 | Supervised text/tag/co-occurrence ranker vs tag Jaccard (magic) | magic | data/annotations/refined/magic_pairs.json | -- | pre-registered; run in the results commit **[incomplete]** | [0080](0080_functional_ranker.yaml) |

## Key Insights (cross-cutting)

1. **Co-occurrence = complement, not substitute.** Functional AUC 0.317 on co-occurrence embeddings. For substitution tasks, zero out embed+jaccard and rely on text_embed+functional. (0002, 0007, 0012)

2. **Data quality > quantity.** Pokemon 10.8x more pairs barely moved nDCG. Tournament decks are homogeneous. (0003)

3. **Card context essential for LLM annotations.** Error rate 16% -> 1% when oracle text included in prompts. (0009)

4. **BPR wrong for dense graphs.** Random negatives are mostly connected nodes. Reconstruction loss (weighted MSE) is correct. (0012)

5. **LightGCN sweep eval was inflated.** Inline eval showed 0.545 but canonical eval shows 0.095 (worse than v5 fused 0.154). Inline eval ranked within annotation set (biased); canonical eval checks if ground-truth cards appear in top-10. Always verify with canonical eval. (0004)

6. **Mode-aware training is critical.** Using substitution instruction for synergy pairs poisons the objective. Route pairs by mode to correct instruction prefixes. (0005)

## CORRECTION (2026-03-22): Duplicate annotations affected nDCG

Test set annotations contained 43-76% duplicates from multi-model IAA.
Experiment 0052 records inflation for three selected before/after comparisons.
Other results from the period require their own snapshot and provenance checks.

### Historical baselines (deduped test sets):
| Embedding | Magic sub | Pokemon sub | YuGiOh sub |
|-----------|-----------|-------------|------------|
| v5_fused (deployed) | 0.099 | 0.075 | 0.157 |
| MetaPath2Vec selective 160ep | 0.045 | 0.024 | 0.157 |
| MetaPath2Vec v2 all-types | 0.045 | 0.025 | 0.157 |

v5_fused REMAINS the best embedding for Magic and Pokemon.
MetaPath2Vec ties YuGiOh but loses on Magic/Pokemon.

### 2026-03-22/23 session findings (experiments 0052-0054)

- **0052**: three recorded comparisons changed by 78-101% relative to the post-dedup score. Incomplete snapshot provenance limits extrapolation to other runs.
- **0053**: deployed v7_fused (0.102) is a 2.5-sigma outlier from its distribution mean (0.094). Strategy: train N seeds, deploy best.
- **0054**: HGT fits on A10G (17GB/24GB) but link prediction objective does not produce similarity-preserving embeddings. Needs contrastive loss.

### Spectral propagation (ProNE): new best deterministic result

ProNE spectral propagation on the v7 edgelist produces Magic sub nDCG **0.1067** -- the new best single-model result and fully deterministic (no random walks, no seed sensitivity). This makes it a strong baseline and a candidate for replacing PecanPy in the production pipeline.

### nDCG convergence: annotation coverage was the bottleneck (exp 0058)

After filling 15K top-10 eval holes (~$6), standard nDCG doubled across all games. Pokemon and YuGiOh reached **standard ~= condensed nDCG** (gap < 0.05) for the evaluated embedding and retrieval method. A small gap does not establish label accuracy or coverage for other systems.

**Implication**: further hole-filling may have diminishing returns *for the evaluated ranking*. New embeddings can reshuffle top-K, surfacing unjudged candidates; a small gap does not identify the binding constraint on quality.

**Outer loop**: fill holes -> get true quality -> train better embedding -> fill new holes from reshuffled top-K -> repeat. Convergence of this outer loop is when new-embedding holes don't change the ranking.

**Decision rule**: monitor the convergence gap (`eval_per_mode.py` now reports `[SATURATED]` or `[gap=X]` per mode). When gap < 0.05 for current embedding, train a new one and re-fill.
