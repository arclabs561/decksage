# Experiment Summary

Chronological log of all ML/DS experiments. Each row links to a detailed YAML file.

## Experiments

| ID | Date | Title | Game | Key Metric | Result | File |
|----|------|-------|------|------------|--------|------|
| 0001 | 2026-03-17 | v4 co-occurrence baseline | all | overall nDCG | M:0.151 P:0.049 Y:0.554 | [0001](0001_v4_baseline.yaml) |
| 0002 | 2026-03-17 | v5 fused (enriched + ns=-0.5 + attr) | all | overall nDCG | M:0.156 P:0.247 Y:0.554 | [0002](0002_v5_fused.yaml) |
| 0003 | 2026-03-18 | Pokemon pairs expansion 16K->179K | pokemon | overall nDCG | 0.294 (+19% rel, plateau) | [0003](0003_pokemon_expanded_pairs.yaml) |
| 0004 | 2026-03-19 | LightGCN hyperparameter sweep | magic | overall nDCG | **0.545** (3.5x over v5) | [0004](0004_lightgcn_sweep.yaml) |
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

## Key Insights (cross-cutting)

1. **Co-occurrence = complement, not substitute.** Functional AUC 0.317 on co-occurrence embeddings. For substitution tasks, zero out embed+jaccard and rely on text_embed+functional. (0002, 0007, 0012)

2. **Data quality > quantity.** Pokemon 10.8x more pairs barely moved nDCG. Tournament decks are homogeneous. (0003)

3. **Card context essential for LLM annotations.** Error rate 16% -> 1% when oracle text included in prompts. (0009)

4. **BPR wrong for dense graphs.** Random negatives are mostly connected nodes. Reconstruction loss (weighted MSE) is correct. (0012)

5. **LightGCN dramatically outperforms PecanPy.** 0.545 vs 0.156 nDCG on Magic. Pure neighborhood aggregation > random walk + Word2Vec. (0004 vs 0001)

6. **Mode-aware training is critical.** Using substitution instruction for synergy pairs poisons the objective. Route pairs by mode to correct instruction prefixes. (0005)
