# Training recipes using runctl

# Build runctl
runctl-build:
    cd ../runctl && cargo build --release

# Train embeddings locally with runctl
train-local:
    @echo "Training embeddings locally with runctl..."
    ../runctl/target/release/runctl local src/ml/scripts/improve_training_with_validation_enhanced.py -- \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/trained.wv \
        --dim 128 \
        --walk-length 80 \
        --num-walks 10 \
        --window-size 10 \
        --p 1.0 \
        --q 1.0 \
        --epochs 10 \
        --val-ratio 0.1 \
        --patience 3 \
        --lr 0.025 \
        --lr-decay 0.95

# Train embeddings on AWS with runctl
train-aws instance:
    @echo "Training embeddings on AWS instance {{instance}}..."
    ../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/improve_training_with_validation_enhanced.py \
        s3://games-collections/processed/pairs_large.csv \
        s3://games-collections/embeddings/trained.wv \
        -- \
        --dim 128 \
        --walk-length 80 \
        --num-walks 10 \
        --window-size 10 \
        --p 1.0 \
        --q 1.0 \
        --epochs 10 \
        --val-ratio 0.1 \
        --patience 3 \
        --lr 0.025 \
        --lr-decay 0.95

# Create AWS instance for training
train-aws-create:
    @echo "Creating AWS EC2 instance for training..."
    @../runctl/target/release/runctl aws create --spot g4dn.xlarge

# Run hyperparameter search with runctl
hyperparam-search:
    @./src/ml/scripts/run_hyperparameter_search_runctl_fixed.sh

# Monitor AWS training instance
train-aws-monitor instance:
    ../runctl/target/release/runctl aws monitor {{instance}} --follow

# Continue all improvements
continue-all:
    # Data enrichment (background)
    @echo "Starting Scryfall enrichment (background)..."
    nohup uv run --script src/ml/scripts/enrich_attributes_with_scryfall_optimized.py \
        --input data/processed/card_attributes_minimal.csv \
        --output data/processed/card_attributes_enriched.csv \
        --batch-size 50 > /tmp/enrichment.log 2>&1 &
    
    # Label generation (background)
    @echo "Generating labels..."
    nohup uv run --script src/ml/scripts/generate_labels_for_new_queries_optimized.py \
        --input experiments/test_set_expanded_magic.json \
        --output experiments/test_set_labeled_magic.json \
        --batch-size 5 --checkpoint-interval 5 > /tmp/labeling.log 2>&1 &
    
    @echo "✅ Background tasks started"
    @echo "   Monitor: tail -f /tmp/enrichment.log"
    @echo "   Monitor: tail -f /tmp/labeling.log"

# Check hyperparameter results and prepare training
check-hyperparam:
    @./src/ml/scripts/prepare_training_after_hyperparam.sh

# Train multi-game embeddings with runctl
train-multigame instance:
    @echo "Training multi-game embeddings on AWS instance {{instance}}..."
    ../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/train_multi_game_embeddings.py \
        --output-s3 s3://games-collections/embeddings/ \
        -- \
        --input s3://games-collections/processed/pairs_multi_game.csv \
        --output s3://games-collections/embeddings/multi_game_unified.wv \
        --mode unified

# Train multi-game embeddings locally with validation
train-multigame-local:
    @echo "Training multi-game embeddings locally..."
    uv run --script src/ml/scripts/train_multi_game_validated.py \
        --input data/processed/pairs_multi_game.csv \
        --output data/embeddings/multi_game_validated.wv \
        --dim 128 \
        --walk-length 80 \
        --num-walks 10 \
        --window-size 10 \
        --p 1.0 \
        --q 1.0 \
        --epochs 10 \
        --test-sets magic:experiments/test_set_expanded_magic.json

hyperparam-multigame:
    @echo "Running multi-game hyperparameter search..."
    ./src/ml/scripts/run_multi_game_hyperparameter_search.sh

# Compare embedding methods with runctl
compare-methods instance:
    @echo "Comparing embedding methods on AWS instance {{instance}}..."
    ../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/compare_embedding_methods.py \
        --output-s3 s3://games-collections/experiments/ \
        -- \
        --input s3://games-collections/processed/pairs_large.csv \
        --output-dir s3://games-collections/experiments/method_comparison/ \
        --methods node2vec deepwalk \
        --dim 128

# Train all embeddings with runctl (local)
train-all-local:
    @echo "Training all embedding variants locally with runctl..."
    ../runctl/target/release/runctl local src/ml/scripts/train_all_embeddings.py -- \
        --input data/processed/pairs_large.csv \
        --dim 128

# Train all embeddings with runctl (AWS)
train-all-aws instance:
    @echo "Training all embedding variants on AWS instance {{instance}}..."
    ../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/train_all_embeddings.py \
        --output-s3 s3://games-collections/embeddings/ \
        -- \
        --input s3://games-collections/processed/pairs_large.csv \
        --dim 128

# Train GNN embeddings with runctl
train-gnn instance:
    @echo "Training GNN embeddings on AWS instance {{instance}}..."
    ../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/train_gnn.py \
        --output-s3 s3://games-collections/embeddings/ \
        -- \
        --pairs-csv s3://games-collections/processed/pairs_large.csv \
        --output s3://games-collections/embeddings/gnn_graphsage.wv

# Run evaluation on AWS with runctl
evaluate-aws instance:
    @echo "Running evaluation on AWS instance {{instance}}..."
    ../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/evaluate_all_embeddings.py \
        --output-s3 s3://games-collections/experiments/ \
        -- \
        --test-set s3://games-collections/processed/test_set_canonical_magic.json \
        --embeddings-dir s3://games-collections/embeddings/ \
        --output s3://games-collections/experiments/evaluation_results.json

# Run evaluation locally (with confidence intervals and per-query analysis)
evaluate-local:
    @echo "Running evaluation locally with confidence intervals..."
    uv run --script src/ml/scripts/evaluate_all_embeddings.py \
        --test-set experiments/test_set_expanded_magic.json \
        --embeddings-dir data/embeddings/ \
        --output experiments/evaluation_results_expanded.json \
        --confidence-intervals \
        --per-query

# Comprehensive evaluation (all games + downstream tasks)
evaluate-comprehensive embedding:
    @echo "Running comprehensive evaluation..."
    uv run --script src/ml/scripts/comprehensive_evaluation_pipeline.py \
        --embedding {{embedding}} \
        --output experiments/evaluation_comprehensive.json \
        --test-sets magic:experiments/test_set_expanded_magic.json \
                    pokemon:experiments/test_set_expanded_pokemon.json \
                    yugioh:experiments/test_set_expanded_yugioh.json \
        --downstream

# Train with similarity-based validation
train-local-validated:
    @echo "Training with similarity-based validation..."
    ../runctl/target/release/runctl local src/ml/scripts/improve_training_with_validation_enhanced.py -- \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/trained_validated.wv \
        --dim 128 \
        --walk-length 80 \
        --num-walks 10 \
        --window-size 10 \
        --p 1.0 \
        --q 1.0 \
        --epochs 10 \
        --val-ratio 0.1 \
        --patience 3 \
        --lr 0.025 \
        --lr-decay 0.95 \
        --val-test-set experiments/test_set_expanded_magic.json

# Generate labels with multi-judge IAA
generate-labels-multi-judge:
    @echo "Generating labels with multi-judge IAA tracking..."
    uv run --script src/ml/scripts/generate_labels_multi_judge.py \
        --input experiments/test_set_canonical_magic.json \
        --output experiments/test_set_multi_judge.json \
        --num-judges 3

# Compute IAA for test set
compute-iaa:
    @echo "Computing IAA for test set..."
    uv run --script src/ml/scripts/compute_iaa_for_test_set.py \
        --test-set experiments/test_set_expanded_magic.json \
        --output experiments/iaa_analysis_expanded.json

# Fix vocabulary mismatch
fix-vocab test-set pairs-csv:
    @echo "Fixing vocabulary mismatch..."
    uv run --script src/ml/scripts/fix_vocabulary_mismatch.py \
        --test-set {{test-set}} \
        --pairs-csv {{pairs-csv}} \
        --name-mapping experiments/name_mapping.json \
        --threshold 0.85

# Expand test sets for all games
expand-all-games:
    @echo "Expanding test sets for all games..."
    uv run --script src/ml/scripts/expand_test_set_multi_game.py \
        --games magic pokemon yugioh \
        --num-judges 3 \
        --magic-target 150 \
        --pokemon-target 50 \
        --yugioh-target 50

# Expand test sets further (extended targets)
expand-test-sets-extended:
    @echo "Expanding test sets to extended targets (Magic: 200, Pokemon: 100, Yu-Gi-Oh: 100)..."
    uv run --script src/ml/scripts/expand_test_set_multi_game.py \
        --games magic pokemon yugioh \
        --num-judges 3 \
        --magic-target 200 \
        --pokemon-target 100 \
        --yugioh-target 100
# Expand test set in chunks (background-friendly)
expand-test-set-chunked game:
    @echo "Expanding {{game}} test set in chunks..."
    @uv run --script src/ml/scripts/expand_test_set_chunked.py         --game {{game}}         --chunk-size 25

# Expand all games in chunks (background)
expand-all-games-chunked:
    @echo "Expanding all game test sets in chunks..."
    @uv run --script src/ml/scripts/expand_test_set_chunked.py --game magic --chunk-size 25 &
    @uv run --script src/ml/scripts/expand_test_set_chunked.py --game pokemon --chunk-size 25 &
    @uv run --script src/ml/scripts/expand_test_set_chunked.py --game yugioh --chunk-size 25 &
    @echo "All expansions started in background"
    @echo "Monitor: tail -f expansion_*.log"


# Create downstream test data
create-downstream-tests game:
    @echo "Creating downstream test data for {{game}}..."
    uv run --script src/ml/scripts/create_downstream_test_data.py \
        --game {{game}} \
        --pairs-csv data/processed/pairs_large.csv \
        --test-set experiments/test_set_expanded_{{game}}.json \
        --output-dir experiments/downstream_tests

# Master pipeline (all tasks)
master-pipeline:
    @echo "Running master pipeline..."
    uv run --script src/ml/scripts/master_pipeline.py

# Check vocabulary coverage
check-vocab test-set embedding:
    @echo "Checking vocabulary coverage..."
    uv run --script src/ml/scripts/check_vocabulary_coverage.py \
        --test-set {{test-set}} \
        --embedding {{embedding}} \
        --pairs-csv data/processed/pairs_large.csv \
        --name-mapping experiments/name_mapping.json

# Optimize fusion weights (after embeddings improve)
optimize-fusion embedding:
    @echo "Optimizing fusion weights..."
    uv run --script src/ml/scripts/optimize_fusion_weights.py \
        --embedding {{embedding}} \
        --pairs-csv data/processed/pairs_large.csv \
        --test-set experiments/test_set_canonical_magic.json \
        --output experiments/optimal_fusion_weights.json

# Enhanced labeling (better models + richer context)
generate-labels-enhanced query:
    @echo "Generating labels with enhanced model and context..."
    uv run --script src/ml/scripts/generate_labels_enhanced.py \
        --query {{query}} \
        --card-attrs data/processed/card_attributes_enriched.csv \
        --use-best

# ============================================================================
# Gold Data Refinement
# ============================================================================
# Continuously improve test set quality with more queries and more labels.
# See docs/GOLD_DATA_REFINEMENT.md for complete documentation.
#
# Quality Targets:
# - Label density: 15-25+ labels per query
# - IAA: ≥0.7 (Inter-Annotator Agreement)
# - Coverage: All card types, formats, archetypes
# ============================================================================

# Comprehensive gold data refinement pipeline (all steps)
# Runs: quality analysis → iterative refinement → batch deepening → re-labeling
refine-gold-data input output="experiments/test_set_expanded_magic.json" iterations="3":
    @echo "Running comprehensive gold data refinement pipeline..."
    bash src/ml/scripts/refine_gold_data_pipeline.sh {{input}} {{output}} {{iterations}} 3

# Iteratively refine gold data (expand + deepen + re-label)
# - Expands: Adds new queries per iteration (default: 20)
# - Deepens: Adds more labels to existing queries below target (default: 20 labels)
# - Re-labels: Improves queries with low IAA (<0.7)
# - Checkpoints: Saves progress after each iteration
# Usage: just iterative-refine input="..." output="..." iterations=3 max-queries=20
iterative-refine input output="experiments/test_set_refined.json" iterations="3" max-queries="null":
    @echo "Iteratively refining gold data: {{input}}..."
    uv run --script src/ml/scripts/iterative_refine_gold_data.py \
        --input {{input}} \
        --output {{output}} \
        --iterations {{iterations}} \
        --new-queries-per-iter 20 \
        --num-judges 3 \
        --min-labels-target 20 \
        --min-iaa-target 0.7 \
        $(if [ "{{max-queries}}" != "null" ]; then echo "--max-queries-per-iter {{max-queries}}"; fi)

# Deepen labels for existing queries (add more labels)
# Targets queries below target label count, adds labels using multi-judge system.
# Usage: just deepen-labels input="..." output="..." target=25
deepen-labels input output="experiments/test_set_deepened.json" target="20":
    @echo "Deepening labels for existing queries..."
    uv run --script src/ml/scripts/batch_deepen_labels.py \
        --input {{input}} \
        --output {{output}} \
        --num-judges 3 \
        --target-labels {{target}} \
        --batch-size 10

# Expand queries only (add new queries)
# Adds new queries without deepening existing ones.
# Usage: just expand-queries input="..." output="..." num=30
expand-queries input output="experiments/test_set_expanded.json" num="20":
    @echo "Expanding with {{num}} new queries..."
    uv run --script src/ml/scripts/iterative_refine_gold_data.py \
        --input {{input}} \
        --output {{output}} \
        --iterations 1 \
        --new-queries-per-iter {{num}} \
        --num-judges 3 \
        --no-deepen

# Enhanced query generation (better models + better prompts)
generate-queries-enhanced num-queries:
    @echo "Generating queries with enhanced model..."
    uv run --script src/ml/scripts/generate_queries_enhanced.py \
        --num-queries {{num-queries}} \
        --existing experiments/test_set_canonical_magic.json \
        --use-best \
        --output experiments/enhanced_queries.json

# Expand test set with LLM (generate new queries + labels)

# Generate comprehensive evaluation data (explicit, implicit, synthetic)
generate-comprehensive-eval game="magic":
    @echo "Generating comprehensive evaluation data for {{game}}..."
    uv run --script src/ml/scripts/generate_comprehensive_eval_data.py \
        --pairs-csv data/processed/pairs_large.csv \
        --game {{game}} \
        --embedding data/embeddings/trained_validated.wv \
        --output experiments/test_set_comprehensive_generated_{{game}}.json \
        --explicit-top-n 200 \
        --implicit-top-n 100 \
        --substitution-top-n 150 \
        --synthetic-num 50

# Extract implicit evaluation signals from deck data
extract-implicit-signals game="magic":
    @echo "Extracting implicit evaluation signals for {{game}}..."
    uv run --script src/ml/scripts/extract_implicit_eval_signals.py \
        --game {{game}} \
        --pairs-csv data/processed/pairs_large.csv \
        --output experiments/test_set_implicit_signals_{{game}}.json \
        --sideboard-top-n 100 \
        --temporal-top-n 50 \
        --substitution-top-n 100

# Create synthetic test cases (functional roles, archetype clusters, power levels)
create-synthetic-test-cases game="magic":
    @echo "Creating synthetic test cases for {{game}}..."
    uv run --script src/ml/scripts/create_synthetic_test_cases.py \
        --game {{game}} \
        --pairs-csv data/processed/pairs_large.csv \
        --embedding data/embeddings/trained_validated.wv \
        --output experiments/test_set_synthetic_{{game}}.json \
        --functional-num 30 \
        --archetype-num 40 \
        --power-level-num 20 \
        --format-num 25

# Merge and analyze multiple test sets
merge-test-sets game="magic":
    @echo "Merging and analyzing test sets for {{game}}..."
    uv run --script src/ml/scripts/merge_and_analyze_test_sets.py \
        --test-sets experiments/test_set_expanded_{{game}}.json \
                   experiments/test_set_comprehensive_generated_{{game}}.json \
                   experiments/test_set_synthetic_{{game}}.json \
        --output experiments/test_set_merged_all_sources_{{game}}.json \
        --pairs-csv data/processed/pairs_large.csv \
        --analysis-output experiments/test_set_analysis_all_sources_{{game}}.json \
        --game {{game}}

# Generate all evaluation data (comprehensive + synthetic + merge + evaluate)
generate-all-eval-data game="magic":
    @echo "Generating all evaluation data for {{game}}..."
    just generate-comprehensive-eval {{game}}
    just create-synthetic-test-cases {{game}}
    just merge-test-sets {{game}}
    @echo "Evaluating on merged test set..."
    uv run --script src/ml/scripts/evaluate_all_embeddings.py \
        --test-set experiments/test_set_merged_all_sources_{{game}}.json \
        --output experiments/evaluation_all_sources_{{game}}.json \
        --confidence-intervals
    @echo "Analyzing results..."
    uv run --script src/ml/scripts/analyze_evaluation_results.py \
        --results experiments/evaluation_all_sources_{{game}}.json \
        --output experiments/evaluation_analysis_all_sources_{{game}}.json
    @echo "✅ All evaluation data generated and evaluated for {{game}}"
generate-eval-data game="magic" output="experiments/test_set_comprehensive.json":
    @echo "Generating comprehensive evaluation data for {{game}}..."
    uv run --script src/ml/scripts/generate_comprehensive_eval_data.py \
        --pairs data/processed/pairs_large.csv \
        --game {{game}} \
        --output {{output}} \
        --explicit-top-n 200 \
        --implicit-top-n 100 \
        --substitution-top-n 150 \
        --synthetic-num 50

# Generate with embeddings for better synthetic queries
generate-eval-data-with-embeddings game="magic" output="experiments/test_set_comprehensive.json" embedding="data/embeddings/trained_functional.wv":
    @echo "Generating comprehensive evaluation data with embeddings for {{game}}..."
    uv run --script src/ml/scripts/generate_comprehensive_eval_data.py \
        --pairs data/processed/pairs_large.csv \
        --game {{game}} \
        --output {{output}} \
        --embedding {{embedding}} \
        --explicit-top-n 200 \
        --implicit-top-n 100 \
        --substitution-top-n 150 \
        --synthetic-num 50

# Validate evaluation data
validate-eval-data test-set:
    @echo "Validating evaluation data: {{test-set}}..."
    uv run --script src/ml/scripts/validate_eval_data.py {{test-set}} --verbose
expand-test-set num-queries:
    @echo "Expanding test set with {{num-queries}} new queries..."
    uv run --script src/ml/scripts/expand_test_set_with_llm.py \
        --input experiments/test_set_canonical_magic.json \
        --output experiments/test_set_expanded_magic.json \
        --num-queries {{num-queries}} \
        --num-judges 3 \
        --batch-size 10

# Batch re-label existing queries (improve quality)
batch-relabel:
    @echo "Re-labeling existing queries with multi-judge..."
    uv run --script src/ml/scripts/batch_label_existing_queries.py \
        --input experiments/test_set_canonical_magic.json \
        --output experiments/test_set_relabeled_magic.json \
        --num-judges 3 \
        --min-labels 10 \
        --replace-fallback \
        --batch-size 10

# Full pipeline: expand + improve labels (using shell script for better error handling)
improve-test-set num-queries:
    @echo "Full test set improvement pipeline..."
    bash src/ml/scripts/run_labeling_pipeline.sh {{num-queries}}

# Quick expand (just add queries, no re-labeling)
quick-expand num-queries:
    @echo "Quick expansion: Adding {{num-queries}} queries..."
    uv run --script src/ml/scripts/expand_test_set_with_llm.py \
        --input experiments/test_set_canonical_magic.json \
        --output experiments/test_set_expanded_magic.json \
        --num-queries {{num-queries}} \
        --num-judges 3 \
        --batch-size 10

# Generic wrapper for any script with runctl (Python version)
run-with-runctl script instance:
    @echo "Running {{script}} with runctl on instance {{instance}}..."
    uv run --script src/ml/scripts/train_with_runctl.py {{script}} --instance {{instance}} --output-s3 s3://games-collections/experiments/

# Generic wrapper for any script with runctl (shell version)
run-with-runctl-sh script instance:
    @echo "Running {{script}} with runctl on instance {{instance}}..."
    ./src/ml/scripts/train_with_runctl_wrapper.sh {{script}} {{instance}}

# Unified training interface (creates instance if needed)
train-unified script:
    @echo "Training {{script}} with runctl (will create instance if needed)..."
    uv run --script src/ml/scripts/train_with_runctl.py {{script}} --create --output-s3 s3://games-collections/experiments/

# Legacy train_on_aws_instance.py replacement (uses runctl)
train-aws-legacy:
    @echo "Training with legacy interface (now using runctl)..."
    uv run --script src/ml/scripts/train_on_aws_instance_runctl.py --create

# Generate LLM-based substitution pairs
generate-substitution-pairs-llm game num_pairs:
    @echo "Generating LLM-based substitution pairs for {{game}}..."
    uv run --script src/ml/scripts/generate_substitution_pairs_llm.py \
        --game {{game}} \
        --num-pairs {{num_pairs}} \
        --output experiments/downstream_tests/substitution_{{game}}_llm.json

# Create Oracle text embeddings
create-oracle-embeddings:
    @echo "Creating Oracle text embeddings..."
    uv run --script src/ml/scripts/create_oracle_text_embeddings.py \
        --csv data/processed/card_attributes_enriched.csv \
        --output data/embeddings/oracle_text_embeddings.pkl \
        --model all-MiniLM-L6-v2

# Optimize fusion weights for substitution
optimize-fusion-substitution:
    @echo "Optimizing fusion weights for substitution..."
    uv run --script src/ml/scripts/optimize_fusion_for_substitution.py \
        --embedding data/embeddings/trained_validated.wv \
        --pairs-csv data/processed/pairs_large.csv \
        --test-pairs experiments/downstream_tests/substitution_magic.json \
        --game magic \
        --output experiments/optimized_fusion_substitution.json \
        --use-functional-tags

# Train embeddings with functional objective
train-functional-embeddings:
    @echo "Training embeddings with functional similarity objective..."
    uv run --script src/ml/scripts/train_embeddings_with_functional_objective.py \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/trained_functional.wv \
        --functional-weight 1.0 \
        --tag-threshold 0.2 \
        --epochs 5

# Train improved functional embeddings (with tag Jaccard)
train-functional-improved:
    @echo "Training improved functional embeddings (tag Jaccard weighting)..."
    uv run --script src/ml/scripts/train_embeddings_with_functional_objective.py \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/trained_functional_improved.wv \
        --functional-weight 1.0 \
        --tag-threshold 0.2 \
        --epochs 10 \
        --walk-length 80 \
        --num-walks 10

# Train embeddings with functional + Oracle text
# Train functional+text embeddings (all games)
train-functional-text:
    @echo "Training embeddings with functional tags + Oracle text..."
    uv run --script src/ml/scripts/train_embeddings_with_functional_and_text.py \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/trained_functional_text.wv \
        --functional-weight 1.0 \
        --tag-threshold 0.2 \
        --text-weight 0.5 \
        --text-threshold 0.7 \
        --epochs 10 \
        --walk-length 80 \
        --num-walks 10

# Train functional+text for specific game
train-functional-text-game game:
    @echo "Training functional+text embeddings for {{game}}..."
    uv run --script src/ml/scripts/train_embeddings_with_functional_and_text.py \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/trained_functional_text_{{game}}.wv \
        --game {{game}} \
        --functional-weight 1.0 \
        --tag-threshold 0.2 \
        --text-weight 0.5 \
        --text-threshold 0.7 \
        --epochs 50 \
        --walk-length 80 \
        --num-walks 10 \
        --dimensions 128

# Train functional+text for Magic with runctl on AWS
train-functional-text-magic-runctl instance:
    @echo "Training Magic functional+text embeddings with runctl on AWS..."
    @../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/train_embeddings_with_functional_and_text.py \
        --data-s3 s3://games-collections/processed/ \
        --output-s3 s3://games-collections/embeddings/ \
        --checkpoint-interval 10 \
        -- \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/trained_functional_text_magic.wv \
        --game MTG \
        --functional-weight 1.0 \
        --tag-threshold 0.2 \
        --text-weight 0.5 \
        --text-threshold 0.7 \
        --epochs 50 \
        --walk-length 80 \
        --num-walks 10 \
        --dimensions 128

# Train embeddings with contrastive learning for substitution (enhanced)
train-contrastive-substitution:
    @echo "Training embeddings with contrastive learning for substitution..."
    uv run --script src/ml/scripts/train_embeddings_contrastive_substitution.py \
        --input data/processed/pairs_large.csv \
        --substitution experiments/downstream_tests/substitution_magic_expanded_100.json \
        --output data/embeddings/trained_contrastive_substitution.wv \
        --positive-weight 10.0 \
        --negative-weight 0.1 \
        --epochs 15 \
        --walk-length 80 \
        --num-walks 10

# Train embeddings with triplet loss for substitution (research-based)
train-triplet-substitution:
    @echo "Training embeddings with triplet loss for substitution..."
    uv run --script src/ml/scripts/train_embeddings_triplet_substitution.py \
        --input data/processed/pairs_large.csv \
        --substitution experiments/downstream_tests/substitution_magic_expanded_100.json \
        --output data/embeddings/trained_triplet_substitution.wv \
        --margin 1.0 \
        --epochs 20 \
        --batch-size 32 \
        --learning-rate 0.001

# Train triplet with runctl on AWS (faster, GPU-enabled)
train-triplet-runctl instance:
    @echo "Training triplet embeddings with runctl on AWS..."
    @../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/train_embeddings_triplet_substitution.py \
        --data-s3 s3://games-collections/processed/ \
        --output-s3 s3://games-collections/embeddings/ \
        --checkpoint-interval 5 \
        -- \
        --input data/processed/pairs_large.csv \
        --substitution experiments/downstream_tests/substitution_magic_expanded_100.json \
        --output data/embeddings/trained_triplet_substitution.wv \
        --margin 1.0 \
        --epochs 20 \
        --batch-size 32 \
        --learning-rate 0.001

# Train embeddings with heterogeneous graph approach (research-based)
train-heterogeneous-substitution:
    @echo "Training embeddings with heterogeneous graph for substitution..."
    uv run --script src/ml/scripts/train_embeddings_heterogeneous_substitution.py \
        --input data/processed/pairs_large.csv \
        --substitution experiments/downstream_tests/substitution_magic_expanded_100.json \
        --output data/embeddings/trained_heterogeneous_substitution.wv \
        --dimensions 128 \
        --epochs 50 \
        --learning-rate 0.001

# Train heterogeneous with runctl on AWS (faster, GPU-enabled)
train-heterogeneous-runctl instance:
    @echo "Training heterogeneous embeddings with runctl on AWS..."
    @../runctl/target/release/runctl aws train {{instance}} \
        src/ml/scripts/train_embeddings_heterogeneous_substitution.py \
        --data-s3 s3://games-collections/processed/ \
        --output-s3 s3://games-collections/embeddings/ \
        --checkpoint-interval 10 \
        -- \
        --input data/processed/pairs_large.csv \
        --substitution experiments/downstream_tests/substitution_magic_expanded_100.json \
        --output data/embeddings/trained_heterogeneous_substitution.wv \
        --dimensions 128 \
        --epochs 50 \
        --learning-rate 0.001

# Implement all research-based improvements
implement-research-improvements:
    @echo "Implementing research-based improvements..."
    uv run --script src/ml/scripts/implement_research_improvements.py \
        --base-test-set experiments/test_set_expanded_magic.json \
        --output-dir experiments/research_improvements \
        --games magic pokemon yugioh \
        --num-judges 5 \
        --min-agreement 0.65 \
        --review-fraction 0.15


# Test different fusion aggregators
test-fusion-aggregators:
    @echo "Testing fusion aggregators on substitution task..."
    uv run --script src/ml/scripts/test_fusion_aggregators.py \
        --embedding data/embeddings/trained_functional.wv \
        --pairs-csv data/processed/pairs_large.csv \
        --test-pairs experiments/downstream_tests/substitution_magic.json \
        --game magic \
        --output experiments/fusion_aggregator_comparison.json \
        --use-functional-tags

# Optimize fusion for all aggregators
optimize-fusion-all-aggregators:
    @echo "Optimizing fusion weights for all aggregation methods..."
    uv run --script src/ml/scripts/optimize_fusion_all_aggregators.py \
        --embedding data/embeddings/trained_functional.wv \
        --pairs-csv data/processed/pairs_large.csv \
        --test-pairs experiments/downstream_tests/substitution_magic.json \
        --game magic \
        --output experiments/optimized_fusion_all_aggregators.json \
        --use-functional-tags

# Compare all embedding variants comprehensively
compare-all-embeddings:
    @echo "Comparing all embedding variants..."
    uv run --script src/ml/scripts/compare_all_embeddings.py \
        --test-set experiments/test_set_expanded_magic.json \
        --pairs-csv data/processed/pairs_large.csv \
        --name-mapping experiments/name_mapping.json \
        --substitution-test experiments/downstream_tests/substitution_magic.json \
        --output experiments/comprehensive_embedding_comparison.json

# Report LLM costs
report-llm-costs reports-dir output:
    @echo "Aggregating LLM cost reports..."
    uv run --script src/ml/scripts/report_llm_costs.py \
        --reports-dir {{reports-dir}} \
        --output {{output}}

# List all runctl commands
list-runctl:
    @echo "Available runctl commands:"
    @echo "  just runctl-build          - Build runctl"
    @echo "  just train-local           - Train locally"
    @echo "  just train-aws <instance>  - Train on AWS"
    @echo "  just train-aws-create     - Create AWS instance"
    @echo "  just train-aws-monitor <instance> - Monitor training"
    @echo "  just hyperparam-search     - Run hyperparameter search"
    @echo "  just train-multigame <instance> - Multi-game training"
    @echo "  just hyperparam-multigame - Multi-game hyperparameter search"
    @echo "  just compare-methods <instance> - Compare embedding methods"
    @echo "  just train-all-local       - Train all variants locally"
    @echo "  just train-all-aws <instance> - Train all variants on AWS"
    @echo "  just train-gnn <instance>  - Train GNN embeddings"
    @echo "  just evaluate-aws <instance> - Run evaluation"
    @echo "  just run-with-runctl <script> <instance> - Generic wrapper"
    @echo "  just evaluate-local        - Run evaluation locally"

# Check runctl status
runctl-status:
    @./scripts/check_runctl_status.sh

# Quick runctl status via runctl itself
runctl-status-quick:
    @../runctl/target/release/runctl status

# Review S3 buckets
review-s3:
    @echo "Reviewing S3 bucket contents..."
    @bash scripts/review_s3_buckets.sh

# Sync all data to S3
sync-s3:
    @echo "Syncing all data to S3..."
    @bash scripts/sync_all_to_s3.sh

# Sync specific directory to S3
sync-s3-dir dir:
    @echo "Syncing {{dir}} to S3..."
    @aws s3 sync {{dir}}/ s3://games-collections/{{dir}}/ --exclude "*.tmp" --exclude "*.log" --exclude "__pycache__/*"

# Comprehensive monitoring
monitor:
    @echo "Monitoring all active tasks..."
    @python3 scripts/monitor_comprehensive.py

# Add triplet to comparison when ready
add-triplet:
    @echo "Adding triplet to comparison..."
    @uv run --script src/ml/scripts/add_triplet_to_comparison.py

# Deploy heterogeneous as production
deploy-heterogeneous:
    @echo "Deploying heterogeneous as production model..."
    @python3 -c "from pathlib import Path; import shutil, json; from datetime import datetime; h=Path('data/embeddings/trained_heterogeneous_substitution.wv'); p=Path('data/embeddings/production.wv'); b=Path('data/embeddings/backups'); b.mkdir(exist_ok=True); [shutil.copy2(p, b/f'production_{datetime.now().strftime(\"%Y%m%d_%H%M%S\")}.wv') for _ in [1] if p.exists()]; shutil.copy2(h, p); print('✅ Deployed heterogeneous as production.wv')"

# Evaluate all embeddings on all games
evaluate-all-games:
    @echo "Evaluating all embeddings on all games..."
    @uv run --script src/ml/scripts/evaluate_all_games.py

# Train game-specific embeddings (Option 1: recommended)
train-game-specific game:
    @echo "Training game-specific embeddings for {{game}}..."
    @uv run --script src/ml/scripts/train_game_specific_embeddings.py \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/{{game}}_game_specific.wv \
        --game {{game}} \
        --dim 128 \
        --epochs 50

# Train all game-specific embeddings
train-all-game-specific:
    @echo "Training game-specific embeddings for all games..."
    @just train-game-specific magic &
    @just train-game-specific pokemon &
    @just train-game-specific yugioh &
    @echo "All game-specific training started in background"
    @echo "Monitor: tail -f *_game_specific_training.log"

# Compare game-specific vs multi-game embeddings
compare-game-specific-vs-multigame:
    @echo "Comparing game-specific vs multi-game embeddings..."
    @uv run --script src/ml/scripts/compare_game_specific_vs_multigame.py

# Monitor until all training completes
monitor-completion:
    @echo "Monitoring until all training completes..."
    @python3 scripts/monitor_completion.py

# Run comprehensive final evaluation
evaluate-final:
    @echo "Running comprehensive final evaluation..."
    @uv run --script src/ml/scripts/comprehensive_final_evaluation.py

# View comprehensive research documentation
view-research-docs:
    @echo "Research Documentation:"
    @echo "  - docs/RESEARCH_COMPREHENSIVE.md: Complete research synthesis with quotes"
    @echo "  - docs/ANNOTATION_QUALITY_GUIDE.md: Annotation best practices"
    @echo "  - docs/NODE2VEC_LIMITATIONS.md: Why Node2Vec fails for functional similarity"
    @echo "  - docs/IMPLEMENTATION_ROADMAP.md: Research-based implementation plan"
    @echo "  - RESEARCH_REFERENCES.md: Complete bibliography (50+ references)"
    @echo ""
    @echo "Opening documentation..."
    @fd -e md docs | head -5

# Continue with all improvements (orchestrates key next steps)
continue-all-improvements:
    @echo "======================================================================"
    @echo "CONTINUING WITH ALL IMPROVEMENTS"
    @echo "======================================================================"
    @echo ""
    @echo "Phase 1: Test Set Expansion"
    @echo "  Running: just expand-test-sets-extended"
    @just expand-test-sets-extended
    @echo ""
    @echo "Phase 2: Substitution Embedding Training"
    @echo "  Training triplet loss embeddings..."
    @just train-triplet-substitution
    @echo ""
    @echo "  Training heterogeneous graph embeddings..."
    @just train-heterogeneous-substitution
    @echo ""
    @echo "Phase 3: Comprehensive Evaluation"
    @echo "  Comparing all embedding variants..."
    @just compare-all-embeddings
    @echo ""
    @echo "✅ All improvements completed!"

# Enhance multi-judge labeling with comprehensive IAA tracking
enhance-multi-judge-iaa:
    @echo "Enhancing multi-judge labeling with IAA tracking..."
    uv run --script src/ml/scripts/enhance_multi_judge_with_iaa.py \
        --test-set experiments/test_set_expanded_magic.json \
        --output experiments/test_set_expanded_magic_enhanced.json \
        --num-judges 5 \
        --min-agreement 0.65 \
        --re-annotate-threshold 0.60


# Enhanced evaluation system
generate-massive-eval-data game="magic":
    uv run src/ml/scripts/generate_massive_eval_data.py \
        --game {{game}} \
        --pairs-csv data/processed/pairs_large.csv \
        --embedding data/embeddings/trained_validated.wv \
        --output experiments/test_set_massive_{{game}}.json \
        --additional-synthetic 300 \
        --include-all-existing

enhanced-evaluate embedding="data/embeddings/trained_validated.wv" test-set="experiments/test_set_ultimate_magic.json" output="experiments/evaluation_enhanced.json":
    uv run src/ml/scripts/enhanced_evaluation_system.py \
        --embedding {{embedding}} \
        --test-set {{test-set}} \
        --output {{output}} \
        --name-mapping experiments/name_mapping.json \
        --top-k 10

generate-all-enhanced game="magic":
    # Generate comprehensive data
    just generate-comprehensive-eval \
        --game {{game}} \
        --explicit-top-n 400 \
        --implicit-top-n 200 \
        --substitution-top-n 300 \
        --synthetic-num 200
    # Generate synthetic data
    just create-synthetic-test-cases \
        --game {{game}} \
        --functional-num 100 \
        --archetype-num 150 \
        --power-level-num 80 \
        --format-num 70
    # Merge all
    uv run src/ml/scripts/merge_and_analyze_test_sets.py \
        --test-sets experiments/test_set_ultimate_{{game}}.json \
            experiments/test_set_comprehensive_generated_{{game}}_v3.json \
            experiments/test_set_synthetic_{{game}}_v3.json \
        --output experiments/test_set_massive_ultimate_{{game}}.json \
        --pairs-csv data/processed/pairs_large.csv \
        --analysis-output experiments/test_set_analysis_massive_ultimate_{{game}}.json \
        --game {{game}}
    # Evaluate
    just enhanced-evaluate \
        --embedding data/embeddings/trained_validated.wv \
        --test-set experiments/test_set_massive_ultimate_{{game}}.json \
        --output experiments/evaluation_enhanced_massive_{{game}}.json


# Dataset health check
dataset-health:
    #!/usr/bin/env python3
    python3 scripts/dataset_health_check.py

# Validate datasets
validate-datasets:
    #!/usr/bin/env python3
    python3 scripts/validate_datasets.py --all

# Monitor game-specific training continuously
monitor-game-specific:
    @echo "Starting continuous monitoring..."
    @python3 << 'PYTHON_EOF'
import time
import json
from pathlib import Path
from datetime import datetime

def get_log_tail(log_path, n_lines):
    if not log_path.exists():
        return []
    with open(log_path) as f:
        lines = f.readlines()
        return lines[-n_lines:] if len(lines) >= n_lines else lines

def check_training_status(game):
    log = Path(f"{game}_game_specific_training.log")
    emb = Path(f"data/embeddings/{game}_game_specific.wv")
    
    status = {"game": game, "running": False, "complete": False, "error": False, "progress": "", "size_mb": 0.0}
    
    if emb.exists():
        status["complete"] = True
        status["size_mb"] = emb.stat().st_size / (1024 * 1024)
        return status
    
    if not log.exists():
        return status
    
    status["running"] = True
    lines = get_log_tail(log, 10)
    
    for line in lines:
        if "ERROR" in line or "Error" in line or "Traceback" in line:
            status["error"] = True
            status["progress"] = line.strip()[:80]
            return status
    
    for line in lines:
        if "Saved" in line or "Complete" in line:
            status["complete"] = True
            status["progress"] = line.strip()[:80]
            return status
    
    for line in reversed(lines):
        if "EPOCH" in line:
            status["progress"] = line.strip()[:80]
            break
        elif "Generating random walks" in line:
            status["progress"] = "Generating walks..."
            break
        elif "Filtered to" in line:
            status["progress"] = line.strip()[:80]
            break
    
    if not status["progress"]:
        status["progress"] = lines[-1].strip()[:80] if lines else "Starting..."
    
    return status

games = ["magic", "pokemon", "yugioh"]
iteration = 0

try:
    while True:
        iteration += 1
        print(f"\n[{iteration}] {datetime.now().strftime('%H:%M:%S')} - Status")
        print("-" * 70)
        
        all_complete = True
        for game in games:
            status = check_training_status(game)
            if status["complete"]:
                print(f"✅ {game.upper():10s}: Complete ({status['size_mb']:.1f} MB)")
            elif status["error"]:
                print(f"❌ {game.upper():10s}: ERROR - {status['progress']}")
                all_complete = False
            elif status["running"]:
                print(f"⏳ {game.upper():10s}: {status['progress']}")
                all_complete = False
            else:
                print(f"⏸️  {game.upper():10s}: Not started")
                all_complete = False
        
        if all_complete:
            print("\n✅ ALL COMPLETE!")
            break
        
        time.sleep(30)
except KeyboardInterrupt:
    print("\n\n⚠️  Monitoring stopped")
PYTHON_EOF
