# ============================================================================
# Development & Testing
# ============================================================================

# Run all tests (parallel by default; override with NPROC=N)
test nproc='':
    #!/usr/bin/env bash
    if [ -n "{{nproc}}" ]; then
        . .venv/bin/activate && pytest -n {{nproc}}
    else
        . .venv/bin/activate && pytest
    fi

# Run tests on a single file quickly
test-quick:
    #!/usr/bin/env bash
    . .venv/bin/activate && pytest -q src/ml/tests/test_constants.py

# Re-run failing tests first (then the rest)
test-failed-first nproc='':
    #!/usr/bin/env bash
    if [ -n "{{nproc}}" ]; then
        . .venv/bin/activate && pytest --ff -n {{nproc}}
    else
        . .venv/bin/activate && pytest --ff
    fi

# Run only tests that failed in the last run
test-last-failed:
    #!/usr/bin/env bash
    . .venv/bin/activate && pytest --lf

# Run tests with coverage
test-cov nproc='':
    #!/usr/bin/env bash
    if [ -n "{{nproc}}" ]; then
        . .venv/bin/activate && pytest --cov=src/ml --cov-report=term-missing -n {{nproc}}
    else
        . .venv/bin/activate && pytest --cov=src/ml --cov-report=term-missing
    fi

# Run Tier 0 & Tier 1 validation tests
test-tier0-tier1:
    #!/usr/bin/env bash
    # Run tests for Tier 0 & Tier 1 validation scripts (fast tests only)
    uv run pytest src/ml/tests/test_tier0_tier1_validation.py \
        src/ml/tests/test_validate_deck_quality.py \
        -v \
        -m "not slow"

# ============================================================================
# Architecture Validation
# ============================================================================

# Check for hardcoded paths (blocking)
check-paths:
    #!/usr/bin/env bash
    python3 scripts/validation/check_hardcoded_paths.py $(git diff --name-only --diff-filter=ACMR HEAD | grep '\.py$' || echo "")

# Check for unsafe data writes (non-blocking)
check-lineage:
    #!/usr/bin/env bash
    python3 scripts/validation/check_lineage_usage.py $(git diff --name-only --diff-filter=ACMR HEAD | grep '\.py$' || echo "") || true

# Check for unvalidated deck loads (non-blocking)
check-schema:
    #!/usr/bin/env bash
    python3 scripts/validation/check_schema_validation.py $(git diff --name-only --diff-filter=ACMR HEAD | grep '\.py$' || echo "") || true

# Run all architecture checks
check-architecture:
    #!/usr/bin/env bash
    echo "Checking hardcoded paths..."
    just check-paths
    echo ""
    echo "Checking lineage usage..."
    just check-lineage
    echo ""
    echo "Checking schema validation..."
    just check-schema

# Run architecture validation tests
test-architecture:
    #!/usr/bin/env bash
    uv run pytest tests/test_lineage_validation.py tests/test_schema_validation.py -v

# Count adoption metrics
check-adoption:
    #!/usr/bin/env bash
    echo "Files using safe_write:"
    rg "safe_write" --type py | wc -l
    echo ""
    echo "Files using validate_deck_record:"
    rg "validate_deck_record" --type py | wc -l
    echo ""
    echo "Files using DeckExport:"
    rg "DeckExport" --type py | wc -l

# Run all Tier 0 & Tier 1 tests (including slow)
test-tier0-tier1-all:
    #!/usr/bin/env bash
    # Run all tests including slow integration tests
    uv run pytest src/ml/tests/test_tier0_tier1_validation.py \
        src/ml/tests/test_validate_deck_quality.py \
        -v

# Validate integration between Tier 0 & Tier 1 components
validate-integration game='magic':
    #!/usr/bin/env bash
    # Validate that all Tier 0 & Tier 1 components work together
    uv run --script src/ml/scripts/validate_integration.py \
        --game {{game}} \
        --workflow \
        --components

# Complete validation and testing (prerequisites + tests + integration + validation)
validate-complete:
    #!/usr/bin/env bash
    # Run complete validation and testing suite
    ./scripts/testing/validate_tier0_tier1_complete.sh

# Run slow/integration tests only
test-slow nproc='':
    #!/usr/bin/env bash
    if [ -n "{{nproc}}" ]; then
        . .venv/bin/activate && pytest -m "slow or integration" -n {{nproc}}
    else
        . .venv/bin/activate && pytest -m "slow or integration"
    fi

# Run API tests
test-api:
    #!/usr/bin/env bash
    . .venv/bin/activate && pytest src/ml/tests/test_api_basic.py src/ml/tests/test_api_smoke.py

# Run integration tests
test-integration:
    #!/usr/bin/env bash
    . .venv/bin/activate && pytest -m integration

# Code Quality
lint:
    #!/usr/bin/env bash
    uv run ruff check src/ml

format:
    #!/usr/bin/env bash
    uv run ruff format src/ml

# Pre-commit hooks (using prek - fast pre-commit alternative)
pre-commit-install:
    #!/usr/bin/env bash
    # Install hooks using prek (preferred) or pre-commit (fallback)
    export PATH="$HOME/.local/bin:$PATH"
    if command -v prek >/dev/null 2>&1; then
      prek install
      prek install --hook-type pre-push
    elif command -v pre-commit >/dev/null 2>&1; then
      pre-commit install
      pre-commit install --hook-type pre-push
    else
      echo "Neither prek nor pre-commit found. Run: ./scripts/setup-dev.sh"
      exit 1
    fi

pre-commit-run:
    #!/usr/bin/env bash
    # Run hooks on all files (prek preferred, pre-commit fallback)
    export PATH="$HOME/.local/bin:$PATH"
    if command -v prek >/dev/null 2>&1; then
      prek run --all-files
    elif command -v pre-commit >/dev/null 2>&1; then
      pre-commit run --all-files
    else
      echo "Neither prek nor pre-commit found. Run: ./scripts/setup-dev.sh"
      exit 1
    fi

pre-commit-update:
    #!/usr/bin/env bash
    # Update hooks to latest versions
    export PATH="$HOME/.local/bin:$PATH"
    if command -v prek >/dev/null 2>&1; then
      prek auto-update
    elif command -v pre-commit >/dev/null 2>&1; then
      pre-commit autoupdate
    else
      echo "Neither prek nor pre-commit found. Run: ./scripts/setup-dev.sh"
      exit 1
    fi

pre-commit:
    #!/usr/bin/env bash
    # Run hooks on staged files (default behavior)
    export PATH="$HOME/.local/bin:$PATH"
    if command -v prek >/dev/null 2>&1; then
      prek run
    elif command -v pre-commit >/dev/null 2>&1; then
      pre-commit run
    else
      echo "Neither prek nor pre-commit found. Run: ./scripts/setup-dev.sh"
      exit 1
    fi

# Development
sync:
    uv sync

clean:
    #!/usr/bin/env bash
    find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name '*.pyc' -delete

# ============================================================================
# Data Pipeline (Legacy - Use runctl for training)
# ============================================================================

# Legacy pipeline: export -> train -> tune -> serve
pipeline-full:
    #!/usr/bin/env bash
    echo "==> Step 1: Export graph from Go backend"
    cd src/backend && go run cmd/export-graph/main.go ../../pairs.csv
    echo "==> Step 2: Train embeddings"
    . .venv/bin/activate && cd src/ml && python card_similarity_pecan.py --input ../backend/pairs.csv
    echo "==> Step 3: Tune fusion weights"
    . .venv/bin/activate && cd src/ml && python -m ml.fusion_grid_search_runner \
        --embeddings vectors.kv --pairs ../backend/pairs.csv --game magic --step 0.1 --top-k 10
    echo "==> Pipeline complete. Start API with: just serve"

# Train embeddings only (legacy)
pipeline-train:
    #!/usr/bin/env bash
    . .venv/bin/activate && cd src/ml && python card_similarity_pecan.py --input ../backend/pairs.csv

# Start API server
serve embeddings='src/ml/vectors.kv' pairs='src/backend/pairs.csv':
    #!/usr/bin/env bash
    . .venv/bin/activate && EMBEDDINGS_PATH={{embeddings}} PAIRS_PATH={{pairs}} uv run uvicorn src.ml.api.api:app --host 0.0.0.0 --port 8000

# Enrichment
enrich-mtg:
    #!/usr/bin/env bash
    cd src/ml && uv run python card_functional_tagger.py

enrich-pokemon:
    #!/usr/bin/env bash
    cd src/ml && uv run python pokemon_functional_tagger.py

enrich-yugioh:
    #!/usr/bin/env bash
    cd src/ml && uv run python yugioh_functional_tagger.py

enrich-all:
    #!/usr/bin/env bash
    just enrich-mtg &
    just enrich-pokemon &
    just enrich-yugioh &
    wait

# ============================================================================
# Data Extraction (Go backend)
# ============================================================================

# Default variables (override via environment variables)
# Example: JOBS=5 GO_PARALLEL=128 just extract-all

# Extract all supported datasets in parallel
extract-all:
    #!/usr/bin/env bash
    JOBS="${JOBS:-3}"
    DATA_DIR="${DATA_DIR:-src/backend/data-full}"
    CACHE_DIR="${CACHE_DIR:-.cache/blob}"
    echo "==> Extracting all datasets (parallel: $JOBS)"
    mkdir -p "$DATA_DIR" "$CACHE_DIR" "$CACHE_DIR/mtg" "$CACHE_DIR/pokemon" "$CACHE_DIR/ygo"
    just extract-mtg &
    just extract-ygo &
    just extract-pokemon &
    wait
    echo "==> Extract complete"

extract-mtg:
    #!/usr/bin/env bash
    GO_PARALLEL="${GO_PARALLEL:-64}"
    DATA_DIR="${DATA_DIR:-src/backend/data-full}"
    CACHE_DIR="${CACHE_DIR:-.cache/blob}"
    MTG_PAGES="${MTG_PAGES:-200}"
    MTGDECKS_LIMIT="${MTGDECKS_LIMIT:-10000}"
    GOLDFISH_LIMIT="${GOLDFISH_LIMIT:-1000}"
    echo "[MTG] mtgtop8 --pages=$MTG_PAGES --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/mtg" extract mtgtop8 --pages "$MTG_PAGES" --parallel "$GO_PARALLEL"
    echo "[MTG] mtgdecks --limit=$MTGDECKS_LIMIT --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/mtg" extract mtgdecks --limit "$MTGDECKS_LIMIT" --parallel "$GO_PARALLEL"
    echo "[MTG] goldfish --limit=$GOLDFISH_LIMIT --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/mtg" extract goldfish --limit "$GOLDFISH_LIMIT" --parallel "$GO_PARALLEL"

extract-pokemon:
    #!/usr/bin/env bash
    GO_PARALLEL="${GO_PARALLEL:-64}"
    DATA_DIR="${DATA_DIR:-src/backend/data-full}"
    CACHE_DIR="${CACHE_DIR:-.cache/blob}"
    POKEMON_CARD_LIMIT="${POKEMON_CARD_LIMIT:-25000}"
    echo "[Pokemon] pokemontcg-data --limit=$POKEMON_CARD_LIMIT --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/pokemon" extract pokemontcg-data --limit "$POKEMON_CARD_LIMIT" --parallel "$GO_PARALLEL"

extract-pokemon-web:
    #!/usr/bin/env bash
    GO_PARALLEL="${GO_PARALLEL:-64}"
    DATA_DIR="${DATA_DIR:-src/backend/data-full}"
    CACHE_DIR="${CACHE_DIR:-.cache/blob}"
    echo "[Pokemon] limitless-web --limit=2000 --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/pokemon" extract limitless-web --limit 2000 --parallel "$GO_PARALLEL"

extract-ygo:
    #!/usr/bin/env bash
    GO_PARALLEL="${GO_PARALLEL:-64}"
    DATA_DIR="${DATA_DIR:-src/backend/data-full}"
    CACHE_DIR="${CACHE_DIR:-.cache/blob}"
    YGO_TOURNAMENT_START="${YGO_TOURNAMENT_START:-0}"
    YGO_TOURNAMENT_PAGES="${YGO_TOURNAMENT_PAGES:-40}"
    YGO_TOURNAMENT_LIMIT="${YGO_TOURNAMENT_LIMIT:-5000}"
    echo "[YGO] ygoprodeck --section=cards --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/ygo" extract ygoprodeck --section cards --parallel "$GO_PARALLEL"
    echo "[YGO] ygoprodeck-tournament --start=$YGO_TOURNAMENT_START --pages=$YGO_TOURNAMENT_PAGES --limit=$YGO_TOURNAMENT_LIMIT --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/ygo" extract ygoprodeck-tournament \
        --start "$YGO_TOURNAMENT_START" --pages "$YGO_TOURNAMENT_PAGES" \
        --limit "$YGO_TOURNAMENT_LIMIT" --parallel "$GO_PARALLEL"

extract-digimon:
    #!/usr/bin/env bash
    GO_PARALLEL="${GO_PARALLEL:-64}"
    DATA_DIR="${DATA_DIR:-src/backend/data-full}"
    CACHE_DIR="${CACHE_DIR:-.cache/blob}"
    LIMITLESS_DECK_LIMIT="${LIMITLESS_DECK_LIMIT:-5000}"
    echo "[Digimon] digimon-limitless-web --limit=$LIMITLESS_DECK_LIMIT --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/digimon" extract digimon-limitless-web --limit "$LIMITLESS_DECK_LIMIT" --parallel "$GO_PARALLEL"

extract-onepiece:
    #!/usr/bin/env bash
    GO_PARALLEL="${GO_PARALLEL:-64}"
    DATA_DIR="${DATA_DIR:-src/backend/data-full}"
    CACHE_DIR="${CACHE_DIR:-.cache/blob}"
    LIMITLESS_DECK_LIMIT="${LIMITLESS_DECK_LIMIT:-5000}"
    echo "[One Piece] onepiece-limitless-web --limit=$LIMITLESS_DECK_LIMIT --parallel=$GO_PARALLEL"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/onepiece" extract onepiece-limitless-web --limit "$LIMITLESS_DECK_LIMIT" --parallel "$GO_PARALLEL"

extract-riftbound:
    #!/usr/bin/env bash
    GO_PARALLEL="${GO_PARALLEL:-64}"
    DATA_DIR="${DATA_DIR:-src/backend/data-full}"
    CACHE_DIR="${CACHE_DIR:-.cache/blob}"
    LIMITLESS_DECK_LIMIT="${LIMITLESS_DECK_LIMIT:-5000}"
    echo "[Riftbound] riftbound-riftboundgg --limit=$LIMITLESS_DECK_LIMIT --parallel=$GO_PARALLEL"
    echo "Note: First run will download Playwright browsers (~50MB)"
    cd src/backend && go run cmd/dataset/main.go --bucket "file://$(pwd)/$DATA_DIR" --cache "$(pwd)/$CACHE_DIR/riftbound" extract riftbound-riftboundgg --limit "$LIMITLESS_DECK_LIMIT" --parallel "$GO_PARALLEL"

# ETL orchestration
etl-mtg:
    #!/usr/bin/env bash
    just extract-mtg
    just enrich-mtg
    cd src/ml && uv run python card_market_data.py

etl-pokemon:
    #!/usr/bin/env bash
    just extract-pokemon
    just enrich-pokemon

etl-ygo:
    #!/usr/bin/env bash
    just extract-ygo
    just enrich-yugioh

etl-all:
    #!/usr/bin/env bash
    just extract-all
    just enrich-all
    cd src/ml && uv run python card_market_data.py

# ============================================================================
# Runctl Commands (Full Implementation with All Improvements)
# ============================================================================

# Runctl-based training with all improvements
train-runctl-local:
    #!/usr/bin/env bash
    ./scripts/runctl_training.sh local

train-enhanced-local:
    #!/usr/bin/env bash
    ./scripts/training/train_enhanced_runctl_local.sh

train-runctl-aws instance:
    #!/usr/bin/env bash
    ./scripts/runctl_training.sh aws {{instance}}

train-enhanced-aws instance:
    #!/usr/bin/env bash
    ./scripts/training/train_enhanced_runctl.sh aws {{instance}}

train-runctl-runpod instance:
    #!/usr/bin/env bash
    ./scripts/runctl_training.sh runpod {{instance}}

# Runctl-based labeling with GPT-5.2 and enhanced context
label-runctl-local:
    #!/usr/bin/env bash
    ./scripts/runctl_labeling.sh local

label-runctl-aws instance:
    #!/usr/bin/env bash
    ./scripts/runctl_labeling.sh aws {{instance}}

# Runctl-based evaluation with GPT-5.2
eval-runctl-local:
    #!/usr/bin/env bash
    ./scripts/runctl_evaluation.sh local

eval-runctl-aws instance:
    #!/usr/bin/env bash
    ./scripts/runctl_evaluation.sh aws {{instance}}

# Runctl-based testing of all improvements
test-runctl:
    #!/usr/bin/env bash
    ./scripts/runctl_test_all.sh

# Runctl demo of all improvements
demo-runctl:
    #!/usr/bin/env bash
    RUNCTL_BIN="${RUNCTL_BIN:-../runctl/target/release/runctl}"
    if [ -f "$RUNCTL_BIN" ]; then
        "$RUNCTL_BIN" local "src/ml/scripts/demo_improvements_live.py" --
    else
        uv run python src/ml/scripts/demo_improvements_live.py
    fi

# Full pipeline using runctl
pipeline-runctl-local:
    #!/usr/bin/env bash
    ./scripts/runctl_full_pipeline.sh local

pipeline-runctl-aws instance:
    #!/usr/bin/env bash
    ./scripts/runctl_full_pipeline.sh aws {{instance}}

# ============================================================================
# Hybrid Embeddings (GNN + Instruction-Tuned + Co-occurrence)
# Per cursor rules: Use runctl, AWS for big training, --data-s3/--output-s3
# LEAKAGE PREVENTION: All commands use temporal splits by default
# ============================================================================

# Full hybrid training (recommended - auto-detects data source)
# Uses temporal split by default to prevent data leakage
train-hybrid-full-local:
    #!/usr/bin/env bash
    # Local training (slow, for testing only)
    # For production: use train-hybrid-full-aws
    # Temporal split enabled by default (prevents leakage)
    ./scripts/training/train_hybrid_full_with_runctl.sh local

train-hybrid-full-aws instance:
    #!/usr/bin/env bash
    # Full hybrid training (AWS GPU, fast - recommended per cursor rules)
    # Uses --data-s3 and --output-s3 for cloud training
    # Temporal split enabled by default (prevents leakage)
    ./scripts/training/train_hybrid_full_with_runctl.sh aws {{instance}}

# Train GNN embeddings only
train-gnn-local:
    #!/usr/bin/env bash
    # GNN-only training (local, slow)
    ./scripts/training/train_hybrid_gnn_with_runctl.sh local

train-gnn-aws instance:
    #!/usr/bin/env bash
    # GNN-only training (AWS GPU, fast - recommended)
    ./scripts/training/train_hybrid_gnn_with_runctl.sh aws {{instance}}

# Evaluate hybrid system
# Uses train-only graph for Jaccard to prevent leakage
eval-hybrid-local:
    #!/usr/bin/env bash
    # Evaluate hybrid system (local)
    # Temporal split enabled by default (uses train-only graph for Jaccard)
    ./scripts/evaluation/eval_hybrid_with_runctl.sh local

eval-hybrid-aws instance:
    #!/usr/bin/env bash
    # Evaluate hybrid system (AWS - recommended for consistency)
    # Temporal split enabled by default (uses train-only graph for Jaccard)
    ./scripts/evaluation/eval_hybrid_with_runctl.sh aws {{instance}}

# Leakage analysis and prevention
check-leakage:
    #!/usr/bin/env bash
    # Run automated leakage analysis
    uv run python -m ml.evaluation.leakage_analysis \
        --graph data/graphs/incremental_graph.json \
        --decks data/processed/decks_all_final.jsonl \
        --test-set experiments/test_set_canonical_magic.json \
        --output experiments/leakage_analysis_report.json

filter-pairs:
    #!/usr/bin/env bash
    # Filter pairs CSV by timestamp to prevent leakage
    # Use filtered pairs for Node2Vec/PecanPy training
    # Note: Requires decks_all_final.jsonl with timestamps
    uv run python -m ml.scripts.filter_pairs_by_timestamp \
        --pairs data/processed/pairs_large.csv \
        --output data/processed/pairs_train_val_only.csv

export-filtered-edgelist:
    #!/usr/bin/env bash
    # Export filtered edgelist from graph (alternative to filtering pairs CSV)
    # Since pairs_large.csv lacks timestamps, export from graph which has them
    # Use this edgelist for Node2Vec/PecanPy training instead of pairs CSV
    uv run python -m ml.scripts.export_filtered_edgelist_from_graph \
        --graph data/graphs/incremental_graph.json \
        --output data/graphs/train_val_edgelist.edg \
        --min-weight 2

# Full hybrid pipeline
hybrid-pipeline-local:
    #!/usr/bin/env bash
    # Full pipeline (local, slow)
    ./scripts/hybrid_embeddings_pipeline.sh local

hybrid-pipeline-aws instance:
    #!/usr/bin/env bash
    # Full pipeline (AWS GPU, fast - recommended)
    ./scripts/hybrid_embeddings_pipeline.sh aws {{instance}}

# Complete hybrid workflow (setup + train + eval)
hybrid-complete-local:
    #!/usr/bin/env bash
    # Complete workflow: setup + train + eval (local)
    ./scripts/run_hybrid_complete.sh local

hybrid-complete-aws instance:
    #!/usr/bin/env bash
    # Complete workflow: setup + train + eval (AWS - recommended)
    ./scripts/run_hybrid_complete.sh aws {{instance}}

# Train enhanced embeddings with runctl on RunPod (requires instance ID)
train-enhanced-runpod instance:
    #!/usr/bin/env bash
    bash scripts/training/train_enhanced_runctl.sh runpod {{instance}}

# ============================================================================
# Annotation Tools (Python + Rust)
# ============================================================================

# Python: Generate hand annotation batch
annotate-generate game target current:
    #!/usr/bin/env bash
    # Generate annotation batch for hand annotation
    # Usage: just annotate-generate magic 950 940
    # Defaults: 15 candidates/query, 0.4 embedding threshold
    # Edit command below to change candidates-per-query or min-embedding-score
    uv run python -m ml.annotation.hand_annotate generate \
        --game {{game}} \
        --target {{target}} \
        --current {{current}} \
        --pairs data/processed/pairs_large.csv \
        --embeddings data/embeddings/production.wv \
        --test-set experiments/test_set_unified_{{game}}.json \
        --output annotations/hand_batch_{{game}}.yaml \
        --candidates-per-query 15 \
        --min-embedding-score 0.4

# Python: Grade completed annotations
annotate-grade input:
    #!/usr/bin/env bash
    # Grade and validate completed annotations
    # Usage: just annotate-grade annotations/hand_batch_magic.yaml
    uv run python -m ml.annotation.hand_annotate grade \
        --input {{input}}

# Python: Merge annotations to test set
annotate-merge input test_set:
    #!/usr/bin/env bash
    # Merge completed annotations into canonical test set
    # Usage: just annotate-merge annotations/hand_batch_magic.yaml experiments/test_set_canonical_magic.json
    uv run python -m ml.annotation.hand_annotate merge \
        --input {{input}} \
        --test-set {{test_set}}

# Python: Generate LLM similarity annotations
annotate-llm similarity='100' strategy='diverse':
    #!/usr/bin/env bash
    # Generate LLM-powered similarity annotations (JSONL)
    # Usage: just annotate-llm 100 diverse
    uv run python -m ml.annotation.llm_annotator \
        --similarity {{similarity}} \
        --strategy {{strategy}}

# Python: Retrofit existing annotations with downstream fields
annotate-retrofit input output:
    #!/usr/bin/env bash
    # Retrofit existing annotations with downstream task fields
    # Usage: just annotate-retrofit annotations/hand_batch_pokemon.yaml annotations/hand_batch_pokemon_retrofitted.yaml
    uv run python src/ml/scripts/retrofit_annotations_with_downstream_fields.py \
        --input {{input}} \
        --output ${output:-{{input}}.retrofitted.yaml}

# Python: Compute IAA for hand annotations
annotate-iaa input output:
    #!/usr/bin/env bash
    # Compute inter-annotator agreement for hand annotations
    # Usage: just annotate-iaa annotations/hand_batch_magic.yaml experiments/iaa_report.json
    uv run python src/ml/scripts/compute_iaa_for_hand_annotations.py \
        --input {{input}} \
        --output ${output:-experiments/iaa_report.json}

# Python: Validate annotation metadata
annotate-validate input type:
    #!/usr/bin/env bash
    # Validate annotation metadata completeness
    # Usage: just annotate-validate annotations/similarity_annotations.jsonl llm
    #        just annotate-validate annotations/hand_batch_magic.yaml hand
    uv run python src/ml/scripts/validate_annotation_metadata.py \
        --input {{input}} \
        --type ${type:-auto}

# Python: Test annotation workflow end-to-end
annotate-test:
    #!/usr/bin/env bash
    # Run end-to-end tests of annotation system
    uv run python src/ml/scripts/test_annotation_workflow.py

# Python: Prioritize annotation candidates (active learning)
annotate-prioritize game output top-k:
    #!/usr/bin/env bash
    # Prioritize which pairs to annotate next
    # Usage: just annotate-prioritize magic experiments/priorities.json 100
    uv run python src/ml/scripts/prioritize_annotation_candidates.py \
        --game {{game}} \
        --output {{output}} \
        --top-k ${top-k:-100}

# Python: Score annotation quality
annotate-quality input output:
    #!/usr/bin/env bash
    # Score quality of annotations
    # Usage: just annotate-quality annotations/similarity_annotations.jsonl experiments/quality.json
    uv run python src/ml/scripts/score_annotation_quality.py \
        --input {{input}} \
        --output ${output:-experiments/annotation_quality.json}

# Python: Orchestrate annotation workflow
annotate-orchestrate game target dry-run:
    #!/usr/bin/env bash
    # Run full annotation workflow
    # Usage: just annotate-orchestrate magic 100
    #        just annotate-orchestrate magic 100 --dry-run
    uv run python src/ml/scripts/orchestrate_annotation_workflow.py \
        --game {{game}} \
        --target ${target:-100} \
        ${dry-run:+--dry-run}

# Python: Generate comprehensive annotation report
annotate-report output:
    #!/usr/bin/env bash
    # Generate comprehensive annotation system report
    # Usage: just annotate-report experiments/annotation_report.json
    uv run python src/ml/scripts/generate_annotation_report.py \
        --output {{output}}

# Python: Benchmark annotation system
annotate-benchmark output:
    #!/usr/bin/env bash
    # Benchmark annotation system performance
    # Usage: just annotate-benchmark experiments/annotation_benchmark.json
    uv run python src/ml/scripts/benchmark_annotation_system.py \
        --output {{output}}

# Python: Convert annotations to substitution pairs
annotate-convert input output min-similarity:
    #!/usr/bin/env bash
    # Convert annotations (JSONL or YAML) to substitution pairs for training
    # Usage: just annotate-convert annotations/similarity_annotations.jsonl experiments/substitution_pairs.json 0.8
    # Default min-similarity: 0.8 (pass as third arg if different)
    uv run python -m ml.scripts.convert_annotations_to_substitution_pairs \
        --input {{input}} \
        --output {{output}} \
        --min-similarity ${min_similarity:-0.8} \
        --stats

# Rust annotation tool archived (2025-01-01)
# Was incomplete experiment - couldn't load embeddings/GNN data
# Use Python tools instead (annotate-* commands above)

# ============================================================================
# Foundation Refinement (T0 Items)
# ============================================================================

# Run all foundation refinement items (T0.1, T0.2, T0.3)
refine-foundation game:
    #!/usr/bin/env bash
    # Foundation refinement: test set validation, deck quality, dashboard
    # Usage: just refine-foundation magic
    #        just refine-foundation pokemon
    uv run python -m ml.scripts.refine_foundation --all --game {{game}}

# Validate test set coverage (T0.1)
validate-test-set game:
    #!/usr/bin/env bash
    # Validate test set coverage and compute statistics
    # Usage: just validate-test-set magic
    uv run python -m ml.evaluation.test_set_validation \
        --test-set experiments/test_set_unified_{{game}}.json \
        --min-queries 100 \
        --min-labels 5

# Generate quality dashboard (see line 766 for implementation)

# Expand Pokemon test set to 100 queries
expand-pokemon-test-set:
    #!/usr/bin/env bash
    # Expand Pokemon test set from 58 to 100 queries
    # Usage: just expand-pokemon-test-set
    uv run python -m ml.scripts.expand_pokemon_test_set \
        --target-size 100 \
        --output experiments/test_set_unified_pokemon_expanded.json

# Add format metadata to test set
add-test-set-metadata game:
    #!/usr/bin/env bash
    # Add format/archetype metadata to test set queries
    # Usage: just add-test-set-metadata magic
    uv run python -m ml.scripts.add_format_metadata_to_test_set \
        --test-set experiments/test_set_unified_{{game}}.json \
        --game {{game}} \
        --output experiments/test_set_unified_{{game}}_with_metadata.json

# ============================================================================
# CLI (Python - Recommended)
# ============================================================================

# Run Python CLI command
cli cmd:
    #!/usr/bin/env bash
    # Run Python CLI command (recommended - same ecosystem)
    # Usage: just cli "similar Lightning Bolt --k 5"
    #        just cli "health"
    #        just cli "search lightning --output json"
    uv run decksage {{cmd}}

# ============================================================================
# Data Lineage Validation
# ============================================================================

# Validate data lineage dependencies
validate-lineage:
    #!/usr/bin/env bash
    echo "Validating data lineage..."
    python3 scripts/data_processing/validate_lineage.py

# Regenerate all derived data (Order 1+) from primary sources
regenerate-derived:
    #!/usr/bin/env bash
    echo "Regenerating derived data (Order 1+)..."
    python3 scripts/data_processing/regenerate_derived.py --all

# ============================================================================
# Tier 0 & Tier 1 Validation
# ============================================================================

# Check prerequisites for Tier 0 & Tier 1 scripts
check-prerequisites:
    #!/usr/bin/env bash
    # Check if all required dependencies and files are available
    uv run --script src/ml/scripts/validate_prerequisites.py

# Run all Tier 0 & Tier 1 validations
validate-tier0-tier1 game='magic' num-decks='20' skip-deck='false':
    #!/usr/bin/env bash
    # Run comprehensive validation for Tier 0 & Tier 1 priorities
    # Usage: just validate-tier0-tier1 magic 20 false
    #        just validate-tier0-tier1 magic 10 true  # Skip slow deck validation
    SKIP_FLAG=""
    if [ "{{skip-deck}}" = "true" ]; then
        SKIP_FLAG="--skip-deck-validation"
    fi
    uv run --script src/ml/scripts/run_all_tier0_tier1.py \
        --game {{game}} \
        --num-decks {{num-decks}} \
        $SKIP_FLAG \
        --check-prerequisites

# Quick validation (skip deck validation)
validate-quick game='magic':
    #!/usr/bin/env bash
    # Quick validation without slow deck quality checks
    just validate-tier0-tier1 {{game}} 10 true

# Validate deck quality only
validate-deck-quality game='magic' num-decks='50':
    #!/usr/bin/env bash
    # Validate deck completion quality
    uv run --script src/ml/scripts/validate_deck_quality.py \
        --game {{game}} \
        --num-decks {{num-decks}}

# Generate quality dashboard
quality-dashboard:
    #!/usr/bin/env bash
    # Generate HTML quality dashboard from validation results
    uv run --script src/ml/evaluation/quality_dashboard.py \
        --test-set-validation experiments/test_set_validation.json \
        --completion-validation experiments/deck_quality_validation_magic.json \
        --evaluation-results experiments/hybrid_evaluation_results.json \
        --output experiments/quality_dashboard.html

# ============================================================================
# Pack Scraping & Integration (Booster/Starter/Standard Packs)
# ============================================================================

# Scrape packs for all games
scrape-packs-all limit-per-game='':
    #!/usr/bin/env bash
    # Scrape packs for all games (Magic, Pokemon, Yu-Gi-Oh)
    # Usage: just scrape-packs-all
    #        just scrape-packs-all limit-per-game=50
    LIMIT_FLAG=""
    if [ -n "{{limit-per-game}}" ]; then
        LIMIT_FLAG="--limit-per-game {{limit-per-game}}"
    fi
    uv run python -m ml.scripts.scrape_all_packs $LIMIT_FLAG

# Scrape Magic packs from Scryfall
scrape-packs-magic pack-types='' limit='':
    #!/usr/bin/env bash
    # Scrape Magic packs from Scryfall API
    # Usage: just scrape-packs-magic
    #        just scrape-packs-magic pack-types="booster starter" limit=100
    PACK_TYPES_FLAG=""
    if [ -n "{{pack-types}}" ]; then
        PACK_TYPES_FLAG="--pack-types {{pack-types}}"
    fi
    LIMIT_FLAG=""
    if [ -n "{{limit}}" ]; then
        LIMIT_FLAG="--limit {{limit}}"
    fi
    uv run python -m ml.scripts.scrape_packs_magic $PACK_TYPES_FLAG $LIMIT_FLAG

# Scrape Pokemon packs from TCGdx
scrape-packs-pokemon limit='':
    #!/usr/bin/env bash
    # Scrape Pokemon packs from TCGdx API
    # Usage: just scrape-packs-pokemon
    #        just scrape-packs-pokemon limit=50
    LIMIT_FLAG=""
    if [ -n "{{limit}}" ]; then
        LIMIT_FLAG="--limit {{limit}}"
    fi
    uv run python -m ml.scripts.scrape_packs_pokemon $LIMIT_FLAG

# Scrape Yu-Gi-Oh packs from YGOProDeck
scrape-packs-yugioh limit='':
    #!/usr/bin/env bash
    # Scrape Yu-Gi-Oh packs from YGOProDeck API
    # Usage: just scrape-packs-yugioh
    #        just scrape-packs-yugioh limit=50
    LIMIT_FLAG=""
    if [ -n "{{limit}}" ]; then
        LIMIT_FLAG="--limit {{limit}}"
    fi
    uv run python -m ml.scripts.scrape_packs_yugioh $LIMIT_FLAG

# Integrate pack data into graph
integrate-packs game='' no-pack-edges='' no-pack-metadata='':
    #!/usr/bin/env bash
    # Integrate pack co-occurrence into incremental graph
    # Usage: just integrate-packs
    #        just integrate-packs game=MTG
    #        just integrate-packs no-pack-edges=true  # Only add metadata, not edges
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    NO_EDGES_FLAG=""
    if [ "{{no-pack-edges}}" = "true" ]; then
        NO_EDGES_FLAG="--no-pack-edges"
    fi
    NO_METADATA_FLAG=""
    if [ "{{no-pack-metadata}}" = "true" ]; then
        NO_METADATA_FLAG="--no-pack-metadata"
    fi
    uv run python -m ml.scripts.integrate_packs_into_graph \
        $GAME_FLAG \
        $NO_EDGES_FLAG \
        $NO_METADATA_FLAG

# Full pack pipeline: scrape + integrate
pack-pipeline game='' limit-per-game='':
    #!/usr/bin/env bash
    # Full pipeline: scrape packs then integrate into graph
    # Usage: just pack-pipeline
    #        just pack-pipeline game=MTG limit-per-game=50
    LIMIT_FLAG=""
    if [ -n "{{limit-per-game}}" ]; then
        LIMIT_FLAG="--limit-per-game {{limit-per-game}}"
    fi
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--games {{game}}"
    fi
    echo "==> Step 1: Scraping packs..."
    uv run python -m ml.scripts.scrape_all_packs $GAME_FLAG $LIMIT_FLAG
    echo "==> Step 2: Integrating packs into graph..."
    if [ -n "{{game}}" ]; then
        just integrate-packs game={{game}}
    else
        just integrate-packs
    fi
    echo "==> Step 3: Validating pack data..."
    if [ -n "{{game}}" ]; then
        uv run python -m ml.scripts.validate_pack_data --game {{game}}
    else
        uv run python -m ml.scripts.validate_pack_data
    fi
    echo "==> Pack pipeline complete!"

# Validate pack data quality
validate-packs game='':
    #!/usr/bin/env bash
    # Validate pack data quality and coverage
    # Usage: just validate-packs
    #        just validate-packs game=MTG
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    uv run python -m ml.scripts.validate_pack_data $GAME_FLAG

# Analyze pack coverage and gaps
analyze-pack-coverage game='' top-n='50':
    #!/usr/bin/env bash
    # Analyze pack coverage and identify gaps
    # Usage: just analyze-pack-coverage
    #        just analyze-pack-coverage game=MTG top-n=100
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    TOP_N_FLAG=""
    if [ -n "{{top-n}}" ]; then
        TOP_N_FLAG="--top-n {{top-n}}"
    fi
    uv run python -m ml.scripts.analyze_pack_coverage $GAME_FLAG $TOP_N_FLAG

# Export graph with pack features for GNN
export-graph-packs game='' min-weight='1':
    #!/usr/bin/env bash
    # Export graph edgelist with pack features for GNN training
    # Usage: just export-graph-packs
    #        just export-graph-packs game=MTG min-weight=2
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    MIN_WEIGHT_FLAG=""
    if [ -n "{{min-weight}}" ]; then
        MIN_WEIGHT_FLAG="--min-weight {{min-weight}}"
    fi
    uv run python -m ml.scripts.export_graph_with_pack_features $GAME_FLAG $MIN_WEIGHT_FLAG

# Integrate archetype relationships
integrate-archetypes game='':
    #!/usr/bin/env bash
    # Integrate archetype relationships into graph
    # Usage: just integrate-archetypes
    #        just integrate-archetypes game=MTG
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    uv run python -m ml.scripts.integrate_archetype_relationships $GAME_FLAG

# Integrate card attribute relationships
integrate-attributes game='':
    #!/usr/bin/env bash
    # Integrate card attribute relationships (color, type, keywords, etc.)
    # Usage: just integrate-attributes
    #        just integrate-attributes game=MTG
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    uv run python -m ml.scripts.integrate_card_attributes_relationships $GAME_FLAG

# Enrich card attributes with image URLs (for visual embeddings)
enrich-card-images limit='' test-set-only='':
    #!/usr/bin/env bash
    # Enrich card_attributes_enriched.csv with image URLs from Scryfall API
    # Part of standard data processing pipeline (Order 0-1: Card attributes enrichment)
    # Usage: just enrich-card-images
    #        just enrich-card-images limit=1000
    #        just enrich-card-images test-set-only=true
    ARGS=()
    if [ -n "{{limit}}" ] && [ "{{limit}}" != "" ]; then
        ARGS+=("--limit" "{{limit}}")
    fi
    if [ -n "{{test-set-only}}" ] && [ "{{test-set-only}}" = "true" ]; then
        ARGS+=("--test-set-only")
    fi
    uv run python scripts/data/update_card_data_with_images.py "${ARGS[@]}"

# Integrate tournament performance
integrate-tournament game='':
    #!/usr/bin/env bash
    # Integrate tournament performance data (winning decks get stronger edges)
    # Usage: just integrate-tournament
    #        just integrate-tournament game=MTG
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    uv run python -m ml.scripts.integrate_tournament_performance $GAME_FLAG

# Integrate format legality
integrate-format game='':
    #!/usr/bin/env bash
    # Integrate format legality relationships
    # Usage: just integrate-format
    #        just integrate-format game=MTG
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    uv run python -m ml.scripts.integrate_format_legality $GAME_FLAG

# Integrate all data sources
integrate-all game='':
    #!/usr/bin/env bash
    # Integrate all data sources (packs, archetypes, attributes, tournament, format)
    # Usage: just integrate-all
    #        just integrate-all game=MTG
    GAME_FLAG=""
    if [ -n "{{game}}" ]; then
        GAME_FLAG="--game {{game}}"
    fi
    uv run python -m ml.scripts.integrate_all_data_sources $GAME_FLAG

# ============================================================================
# TypeScript Client & CLI (ARCHIVED - Use Python CLI Instead)
# ============================================================================
#
# TypeScript package archived on 2025-01-01.
# Reason: Frontend uses direct fetch(), Python CLI replaced TypeScript CLI.
# Location: archive/2025-01-01-cleanup/packages/decksage-ts/
#
# If needed for future frontend/Node.js work, restore from archive.
