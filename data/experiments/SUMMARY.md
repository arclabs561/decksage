# Experiment Summary

Chronological log of all ML/DS experiments. Each row links to a detailed YAML file.

## Experiments

| ID | Date | Title | Game | Key Metric | Result | File |
|----|------|-------|------|------------|--------|------|
| 0001 | 2026-03-17 | v4 co-occurrence baseline | all | overall nDCG | M:0.151 P:0.049 Y:0.554 | [0001](0001_v4_baseline.yaml) |
| 0002 | 2026-03-17 | v5 fused (enriched + ns=-0.5 + attr) | all | overall nDCG | M:0.156 P:0.247 Y:0.554 | [0002](0002_v5_fused.yaml) |
| 0003 | 2026-03-18 | Pokemon pairs expansion 16K->179K | pokemon | overall nDCG | 0.294 (+19% rel, plateau) | [0003](0003_pokemon_expanded_pairs.yaml) |
| 0004 | 2026-03-19 | LightGCN hyperparameter sweep | magic | overall nDCG | sweep: 0.545 (inflated), canonical: 0.095 (WORSE than v5 0.154) | [0004](0004_lightgcn_sweep.yaml) |
| 0005 | 2026-03-19 | E5 multi-task fine-tuning | magic | train loss | 0.027 (converged) | [0005](0005_e5_multitask_finetune.yaml) |
| 0006 | 2026-03-19 | Flow-based deck completion | magic | hit@10 | 0.031 (first pass) | [0006](0006_flow_completion.yaml) |
| 0007 | 2026-03-19 | Fusion weight switching fix | all | recall@10 | M:0.38 P:0.38 Y:0.62 | [0007](0007_fusion_weight_fix.yaml) |
| 0008 | 2026-03-16 | Annotation v2 test sets | all | annotated pairs | M:481 P:300 Y:300 | [0008](0008_annotation_v2_test_sets.yaml) |
| 0009 | 2026-03-17 | Card context in annotations | all | error rate | 16% -> 1% | [0009](0009_annotation_card_context.yaml) |
| 0010 | 2026-03-18 | Annotation enrichment | all | enriched pairs | 6,690 total | [0010](0010_annotation_enrichment.yaml) |
| 0011 | 2026-03-15 | OT completion v2 | magic | -- | reformulated (was degenerate) | [0011](0011_ot_completion_v2.yaml) |
| 0012 | 2026-03-17 | LightGCN reconstruction loss | all | -- | BPR collapses, recon works | [0012](0012_lightgcn_reconstruction_loss.yaml) |
| 0013 | 2026-03-17 | Per-mode eval framework | all | -- | eval scripts created | [0013](0013_per_mode_eval.yaml) |
| 0014 | 2026-03-16 | IAA model rotation | all | models | 4-model pool | [0014](0014_iaa_model_rotation.yaml) |
| 0015 | 2026-03-18 | Diverse pair generation | all | pairs | 1,600 (4 sources) | [0015](0015_diverse_pair_generation.yaml) |
| 0016 | 2026-03-18 | Annotation edges export | all | edges | 3,232 exported | [0016](0016_annotation_edges_export.yaml) |
| 0017 | 2026-03-19 | E5 fine-tuned eval | magic | nDCG | within-annotation ranking | [0017](0017_e5_finetuned_eval.yaml) |
| 0018 | 2026-03-19 | LightGCN canonical eval | magic | nDCG | 0.095 (inflated sweep: 0.545) | [0018](0018_lightgcn_canonical_eval.yaml) |
| 0019 | 2026-03-19 | Eval metrics audit | all | -- | recommendations | [0019](0019_metrics_audit.yaml) |
| 0020 | 2026-03-19 | Coverage fix via text embeddings | magic | coverage | 11.6% -> 29% | [0020](0020_catalog_coverage_fix.yaml) |
| 0021 | 2026-03-19 | Stratified nDCG bias check | magic | bias ratio | popular/niche split | [0021](0021_stratified_ndcg.yaml) |
| 0022 | 2026-03-19 | Set/keyword/precon edges | magic | edges | new edge types added | [0022](0022_set_edges.yaml) |
| 0023 | 2026-03-19 | v7 retrain w/ set edges | magic | nDCG | coverage up, nDCG down | [0023](0023_v7_set_edges_retrain.yaml) |
| 0024 | 2026-03-19 | LightGCN collapse root cause | all | -- | trivial solution on sparse graphs | [0024](0024_lightgcn_collapse_diagnosis.yaml) |
| 0025 | 2026-03-19 | Ceiling analysis | magic | ranking | 95.6% optimal, retrieval is bottleneck | [0025](0025_ceiling_analysis.yaml) |
| 0026 | 2026-03-20 | All-games baseline post-fixes | all | nDCG | M:0.156 P:0.294 Y:0.554 | [0026](0026_all_games_baseline_with_fixes.yaml) |
| 0027 | 2026-03-20 | IAA Krippendorff alpha | magic | alpha | 0.43 (judges disagree) | [0027](0027_iaa_krippendorff.yaml) |
| 0028 | 2026-03-20 | Archidekt Commander scrape | magic | pairs | 1.59M from 507 decks | [0028](0028_archidekt_commander_scrape.yaml) |
| 0029 | 2026-03-20 | v8 Commander retrain | magic | nDCG | coverage up, nDCG down | [0029](0029_v8_commander_retrain.yaml) |
| 0030 | 2026-03-20 | MetaPath2Vec first pass | magic | sub nDCG | 0.114 (5ep baseline) | [0030](0030_metapath2vec_first_pass.yaml) |
| 0031 | 2026-03-20 | MetaPath2Vec v2 beats v5 | magic | sub nDCG | 0.177 (+43% over v5) | [0031](0031_metapath2vec_v2_beats_v5.yaml) |
| 0032 | 2026-03-20 | Dual-embedding fusion analysis | magic | nDCG | v5+MP2V = +16% | [0032](0032_fusion_analysis.yaml) |
| 0033 | 2026-03-20 | Data curation audit | magic | -- | dedup, land noise, gaps | [0033](0033_data_curation_audit.yaml) |
| 0034 | 2026-03-20 | rankops CombMNZ vs RRF | magic | nDCG | CombMNZ +10% over RRF | [0034](0034_rankops_fusion_comparison.yaml) |
| 0035 | 2026-03-20 | Commander data scaling | magic | pairs | 3.8M from 2,615 decks | [0035](0035_commander_data_scaling.yaml) |
| 0036 | 2026-03-20 | MetaPath2Vec tuning | magic | sub nDCG | attr fusion hurts | [0036](0036_metapath2vec_tuning.yaml) |
| 0037 | 2026-03-20 | MetaPath2Vec 40ep | magic | sub nDCG | 0.186 (+50% over v5) | [0037](0037_metapath2vec_40epochs.yaml) |
| 0038 | 2026-03-20 | MetaPath2Vec 80ep | magic | sub nDCG | 0.198 (+60% over v5) | [0038](0038_metapath2vec_80epochs.yaml) |
| 0039 | 2026-03-21 | MetaPath2Vec 160ep | magic | sub nDCG | 0.228 (+84% over v5) | [0039](0039_metapath2vec_160epochs.yaml) |

## Key Insights (cross-cutting)

1. **Co-occurrence = complement, not substitute.** Functional AUC 0.317 on co-occurrence embeddings. For substitution tasks, zero out embed+jaccard and rely on text_embed+functional. (0002, 0007, 0012)

2. **Data quality > quantity.** Pokemon 10.8x more pairs barely moved nDCG. Tournament decks are homogeneous. (0003)

3. **Card context essential for LLM annotations.** Error rate 16% -> 1% when oracle text included in prompts. (0009)

4. **BPR wrong for dense graphs.** Random negatives are mostly connected nodes. Reconstruction loss (weighted MSE) is correct. (0012)

5. **LightGCN sweep eval was inflated.** Inline eval showed 0.545 but canonical eval shows 0.095 (worse than v5 fused 0.154). Inline eval ranked within annotation set (biased); canonical eval checks if ground-truth cards appear in top-10. Always verify with canonical eval. (0004)

6. **Mode-aware training is critical.** Using substitution instruction for synergy pairs poisons the objective. Route pairs by mode to correct instruction prefixes. (0005)
