.PHONY: help test test-quick lint format clean sync

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Testing
test:  ## Run all tests (parallel by default; override with NPROC=N)
	@. .venv/bin/activate && pytest $(if $(NPROC),-n $(NPROC),)

test-quick:  ## Run tests on a single file quickly
	@. .venv/bin/activate && pytest -q src/ml/tests/test_constants.py

test-failed-first:  ## Re-run failing tests first (then the rest)
	@. .venv/bin/activate && pytest --ff $(if $(NPROC),-n $(NPROC),)

test-last-failed:  ## Run only tests that failed in the last run
	@. .venv/bin/activate && pytest --lf $(if $(NPROC),-n $(NPROC),)

test-cov:  ## Run tests with coverage (parallel-friendly)
	@. .venv/bin/activate && pytest --cov=src/ml --cov-report=term-missing $(if $(NPROC),-n $(NPROC),)

test-slow:  ## Run slow/integration tests only
	@. .venv/bin/activate && pytest -m "slow or integration" $(if $(NPROC),-n $(NPROC),)

test-api:  ## Run API tests
	@. .venv/bin/activate && pytest src/ml/tests/test_api_basic.py src/ml/tests/test_api_smoke.py

test-integration:  ## Run integration tests
	@. .venv/bin/activate && pytest -m integration

# Code Quality
lint:  ## Run ruff linter
	uv run ruff check src/ml

format:  ## Format code with ruff
	uv run ruff format src/ml

# Development
sync:  ## Sync dependencies with uv
	uv sync

clean:  ## Clean Python cache files
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

# Pipeline orchestration
.PHONY: pipeline-full pipeline-train pipeline-serve

pipeline-full:  ## Run complete pipeline: export -> train -> tune -> serve
	@echo "==> Step 1: Export graph from Go backend"
	cd src/backend && go run cmd/export-graph/main.go ../../pairs.csv
	@echo "==> Step 2: Train embeddings"
	@. .venv/bin/activate && cd src/ml && python card_similarity_pecan.py --input ../backend/pairs.csv
	@echo "==> Step 3: Tune fusion weights"
	@. .venv/bin/activate && cd src/ml && python -m ml.fusion_grid_search_runner \
		--embeddings vectors.kv --pairs ../backend/pairs.csv --game magic --step 0.1 --top-k 10
	@echo "==> Pipeline complete. Start API with: make pipeline-serve"

pipeline-train:  ## Train embeddings only
	@. .venv/bin/activate && cd src/ml && python card_similarity_pecan.py --input ../backend/pairs.csv

pipeline-serve:  ## Start API server
	@. .venv/bin/activate && EMBEDDINGS_PATH=src/ml/vectors.kv PAIRS_PATH=src/backend/pairs.csv uv run uvicorn src.ml.api.api:app --host 0.0.0.0 --port 8000

# Enrichment
.PHONY: enrich-mtg enrich-pokemon enrich-yugioh

enrich-mtg:  ## Enrich MTG cards with functional tags (free)
	@cd src/ml && uv run python card_functional_tagger.py

enrich-pokemon:  ## Enrich Pokemon cards with functional tags (free)
	@cd src/ml && uv run python pokemon_functional_tagger.py

enrich-yugioh:  ## Enrich Yu-Gi-Oh cards with functional tags (free)
	@cd src/ml && uv run python yugioh_functional_tagger.py

# ------------------------------------------------------------
# Data extraction (Go backend) - parallelizable entry points
# Defaults are conservative; override with env vars as needed.
# Example: make extract-all JOBS=3 GO_PARALLEL=64 MTG_PAGES=200
# ------------------------------------------------------------

.PHONY: extract-all extract-mtg extract-pokemon extract-pokemon-web extract-ygo refresh-mtg refresh-ygo refresh-pokemon

# Tuning knobs (override via env)
JOBS ?= 3
GO_PARALLEL ?= 64

# Data directory (file bucket). Override if different.
DATA_DIR ?= src/backend/data-full
CACHE_DIR ?= .cache/blob

# MTG knobs
MTG_PAGES ?= 200
MTGDECKS_LIMIT ?= 10000
GOLDFISH_LIMIT ?= 1000

# Pokemon knobs
POKEMON_CARD_LIMIT ?= 25000

# YGO knobs
YGO_TOURNAMENT_START ?= 0
YGO_TOURNAMENT_PAGES ?= 40
YGO_TOURNAMENT_LIMIT ?= 5000

extract-all:  ## Extract all supported datasets in parallel (no Limitless API)
	@echo "==> Extracting all datasets (parallel: $(JOBS))"
	@mkdir -p $(DATA_DIR) $(CACHE_DIR) $(CACHE_DIR)/mtg $(CACHE_DIR)/pokemon $(CACHE_DIR)/ygo
	@$(MAKE) -j $(JOBS) extract-mtg extract-ygo extract-pokemon
	@echo "==> Extract complete"

extract-mtg:  ## Extract MTG datasets (mtgtop8, mtgdecks, goldfish)
	@echo "[MTG] mtgtop8 --pages=$(MTG_PAGES) --parallel=$(GO_PARALLEL)"
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/mtg extract mtgtop8 --pages $(MTG_PAGES) --parallel $(GO_PARALLEL)
	@echo "[MTG] mtgdecks --limit=$(MTGDECKS_LIMIT) --parallel=$(GO_PARALLEL)"
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/mtg extract mtgdecks --limit $(MTGDECKS_LIMIT) --parallel $(GO_PARALLEL)
	@echo "[MTG] goldfish --limit=$(GOLDFISH_LIMIT) --parallel=$(GO_PARALLEL)"
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/mtg extract goldfish --limit $(GOLDFISH_LIMIT) --parallel $(GO_PARALLEL)

extract-pokemon:  ## Extract Pokemon cards (pokemontcg-data); set POKEMON_TCG_DATA_DIR to reuse clones
	@echo "[Pokemon] pokemontcg-data --limit=$(POKEMON_CARD_LIMIT) --parallel=$(GO_PARALLEL)"
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/pokemon extract pokemontcg-data --limit $(POKEMON_CARD_LIMIT) --parallel $(GO_PARALLEL)

extract-pokemon-web:  ## Extract Pokemon decks via Limitless website (optional fallback)
	@echo "[Pokemon] limitless-web --limit=2000 --parallel=$(GO_PARALLEL)"
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/pokemon extract limitless-web --limit 2000 --parallel $(GO_PARALLEL)

extract-ygo:  ## Extract YGO cards and tournament decks (ygoprodeck, ygoprodeck-tournament)
	@echo "[YGO] ygoprodeck --section=cards --parallel=$(GO_PARALLEL)"
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/ygo extract ygoprodeck --section cards --parallel $(GO_PARALLEL)
	@echo "[YGO] ygoprodeck-tournament --start=$(YGO_TOURNAMENT_START) --pages=$(YGO_TOURNAMENT_PAGES) --limit=$(YGO_TOURNAMENT_LIMIT) --parallel=$(GO_PARALLEL)"
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/ygo extract ygoprodeck-tournament \
		--start $(YGO_TOURNAMENT_START) --pages $(YGO_TOURNAMENT_PAGES) \
		--limit $(YGO_TOURNAMENT_LIMIT) --parallel $(GO_PARALLEL)

# Refresh variants (re-parse without refetch; add --rescrape to force refetch)
refresh-mtg:  ## Refresh MTG datasets (reparse); add RESCRAPE=1 to refetch
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/mtg extract mtgtop8 --reparse $(if $(RESCRAPE),--rescrape,) --pages $(MTG_PAGES) --parallel $(GO_PARALLEL)
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/mtg extract mtgdecks --reparse $(if $(RESCRAPE),--rescrape,) --limit $(MTGDECKS_LIMIT) --parallel $(GO_PARALLEL)
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/mtg extract goldfish --reparse $(if $(RESCRAPE),--rescrape,) --limit $(GOLDFISH_LIMIT) --parallel $(GO_PARALLEL)

refresh-pokemon:  ## Refresh Pokemon cards (reparse); add RESCRAPE=1 to refetch
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/pokemon extract pokemontcg-data --reparse $(if $(RESCRAPE),--rescrape,) --limit $(POKEMON_CARD_LIMIT) --parallel $(GO_PARALLEL)

refresh-ygo:  ## Refresh YGO datasets (reparse); add RESCRAPE=1 to refetch
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/ygo extract ygoprodeck --reparse $(if $(RESCRAPE),--rescrape,) --section cards --parallel $(GO_PARALLEL)
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR))/ygo extract ygoprodeck-tournament --reparse $(if $(RESCRAPE),--rescrape,) \
		--start $(YGO_TOURNAMENT_START) --pages $(YGO_TOURNAMENT_PAGES) \
		--limit $(YGO_TOURNAMENT_LIMIT) --parallel $(GO_PARALLEL)

	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR)) extract ygoprodeck --reparse $(if $(RESCRAPE),--rescrape,) --section cards --parallel $(GO_PARALLEL)
	@cd src/backend && go run cmd/dataset/main.go --bucket file://$(abspath $(DATA_DIR)) --cache $(abspath $(CACHE_DIR)) extract ygoprodeck-tournament --reparse $(if $(RESCRAPE),--rescrape,) \
		--start $(YGO_TOURNAMENT_START) --pages $(YGO_TOURNAMENT_PAGES) \
		--limit $(YGO_TOURNAMENT_LIMIT) --parallel $(GO_PARALLEL)

# ------------------------------------------------------------
# ETL orchestration (Extract -> Enrich). Simple, explicit flows.
# ------------------------------------------------------------

.PHONY: enrich-all price-enrich etl-mtg etl-pokemon etl-ygo etl-all

enrich-all:  ## Run rule-based enrichment for all games
	@$(MAKE) -j 3 enrich-mtg enrich-pokemon enrich-yugioh

price-enrich:  ## Build MTG price database from Scryfall-derived data (optional)
	@cd src/ml && uv run python card_market_data.py

etl-mtg:  ## Extract + enrich MTG (includes price enrichment)
	@$(MAKE) extract-mtg
	@$(MAKE) enrich-mtg
	@$(MAKE) price-enrich

etl-pokemon:  ## Extract + enrich Pokemon (cards + rule tags)
	@$(MAKE) extract-pokemon
	@$(MAKE) enrich-pokemon

etl-ygo:  ## Extract + enrich Yu-Gi-Oh (cards + rule tags)
	@$(MAKE) extract-ygo
	@$(MAKE) enrich-yugioh

etl-all:  ## Extract + enrich all datasets (sequential to ensure availability)
	@$(MAKE) extract-all JOBS=$(JOBS) GO_PARALLEL=$(GO_PARALLEL)
	@$(MAKE) enrich-all
	@$(MAKE) price-enrich

# ------------------------------------------------------------
# Verification & reports
# ------------------------------------------------------------

.PHONY: report-dataset-counts verify-extract etl-smoke

report-dataset-counts:  ## Print object counts per dataset (.zst) using fd
	@echo "==> Reporting counts under $(DATA_DIR)/games"
	@set -e; \
	count(){ c=$(fd -e zst . "$${1}" 2>/dev/null | wc -l | tr -d ' '); printf "%s: %s\n" "$${2}" "$${c}"; }; \
	count "$(DATA_DIR)/games/magic/mtgtop8" "magic/mtgtop8"; \
	count "$(DATA_DIR)/games/magic/mtgdecks" "magic/mtgdecks"; \
	count "$(DATA_DIR)/games/magic/goldfish" "magic/goldfish"; \
	count "$(DATA_DIR)/games/pokemon/pokemontcg-data/cards" "pokemon/pokemontcg-data(cards)"; \
	count "$(DATA_DIR)/games/pokemon/limitless-web" "pokemon/limitless-web"; \
	count "$(DATA_DIR)/games/yugioh/ygoprodeck" "yugioh/ygoprodeck"; \
	count "$(DATA_DIR)/games/yugioh/ygoprodeck-tournament" "yugioh/ygoprodeck-tournament"

verify-extract:  ## Quick sanity: show intended extract cmds and current counts
	@$(MAKE) -n extract-all JOBS=$(JOBS) GO_PARALLEL=$(GO_PARALLEL) MTG_PAGES=$(MTG_PAGES) MTGDECKS_LIMIT=$(MTGDECKS_LIMIT) GOLDFISH_LIMIT=$(GOLDFISH_LIMIT) POKEMON_CARD_LIMIT=$(POKEMON_CARD_LIMIT) YGO_TOURNAMENT_START=$(YGO_TOURNAMENT_START) YGO_TOURNAMENT_PAGES=$(YGO_TOURNAMENT_PAGES) YGO_TOURNAMENT_LIMIT=$(YGO_TOURNAMENT_LIMIT)
	@$(MAKE) report-dataset-counts

etl-smoke:  ## Run small ETL slice (low limits) then report counts
	@$(MAKE) etl-all JOBS=2 GO_PARALLEL=4 MTG_PAGES=1 MTGDECKS_LIMIT=5 GOLDFISH_LIMIT=5 POKEMON_CARD_LIMIT=50 YGO_TOURNAMENT_START=0 YGO_TOURNAMENT_PAGES=1 YGO_TOURNAMENT_LIMIT=10
	@$(MAKE) report-dataset-counts