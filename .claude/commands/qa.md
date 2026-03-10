# /qa -- Real-world quality audit of DeckSage

Evaluate DeckSage's card similarity, search, deck operations, frontend UX, and visual design by running real queries across all three games. This is not a pass/fail test -- it produces a written assessment of what DeckSage does well and where it falls short.

## Execution strategy

- **Parallelize independent checks**: preflight, baseline queries, endpoint tests, and error-path tests can run concurrently once the server is up.
- **Capture exact output**: save command output to temp files so diffs against previous runs are reliable.
- **Time everything**: note wall-clock for each endpoint. Latency regressions matter.
- **Stop early on server failure**: if the server fails to start, report and stop.
- **Read previous reports first**: step 7 requires comparison.
- **Port 8001**: use port 8001 for dev (8000 is often taken by dashboard-exporter).
- **Verify env before starting**: check `.env` paths match actual files. The server loads data at startup -- stale env or stale server = wrong data silently.

## Response schema

API responses use `card` and `similarity` field names (NOT `name`/`score`). Each result has a `metadata` object. Keep this in mind when parsing and reporting results.

## Report convention

Reports go in `qa/reports/qa-YYYY-MM-DD.md` (or `qa-YYYY-MM-DD-rN.md` for multiple runs on the same day). Read any existing reports before starting -- step 7 requires comparing against them.

## Procedure

### 0. Read prior reports

Before starting, read existing QA reports for context:

```bash
# List all existing reports
ls qa/reports/*.md 2>/dev/null
```

Read the most recent report (if any). Extract:
- **Last baseline results**: top-5 for each stable query (for regression comparison in step 7)
- **Open bug checklist**: which bugs were open last run
- **VLM scores**: per-theme and per-dimension scores

Keep this context loaded throughout the run -- you'll compare against it in steps 5-7.

If reports exist from the same day, use `-rN` suffix for the new report (e.g., `qa-2026-03-02-r3.md`).

### 1. Verify environment and start the API server

**Pre-flight env check** (catches stale-server bugs that waste 30+ min):

```bash
# Verify .env paths point to real files
grep '^PAIRS_PATH\|^EMBEDDINGS_PATH' .env | while IFS='=' read -r key val; do
  val="${val#./}"
  if [ ! -f "$val" ]; then echo "MISSING: $key=$val"; fi
done

# If server is already running, verify it loaded the RIGHT data
# (server loads pairs/embeddings at startup -- restarting after env changes is required)
curl -s http://localhost:8001/v1/health?game=yugioh 2>/dev/null | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'YGO cards: {d.get(\"card_count\",\"?\")} graph: {d.get(\"graph_cards\",\"?\")}')
" 2>/dev/null || echo "Server not running"
```

**Start server**:

```bash
cd <repo-root>
# NOTE: `just serve` uses hardcoded old paths and port 8000. Use uvicorn directly with .env:
uv run uvicorn src.ml.api.api:app --host 127.0.0.1 --port 8001 &
API_PID=$!
sleep 5
```

If the server fails to start, stop and report. Check logs for missing embeddings or config issues. Server startup takes ~40s (loads all 3 games + SigLIP + sentence-transformers).

**Gotcha**: If `.env` was changed since last server start, you MUST restart. The server loads all data during startup and does not hot-reload env changes. Always verify via `/v1/health?game=yugioh` that the right data is loaded.

### 2. Preflight checks

```bash
BASE=http://localhost:8001

# Liveness
curl -s $BASE/live | python3 -m json.tool

# Readiness (503 = embeddings not loaded)
curl -s -o /dev/null -w "%{http_code}" $BASE/ready

# Available games
curl -s $BASE/v1/games | python3 -m json.tool

# Per-game health (card counts, embedding dimensions)
curl -s "$BASE/v1/health?game=magic" | python3 -m json.tool
curl -s "$BASE/v1/health?game=pokemon" | python3 -m json.tool
curl -s "$BASE/v1/health?game=yugioh" | python3 -m json.tool
```

Note card counts and embedding dimensions for each game. If any game reports 0 cards, note and proceed with available games.

### 3. Run on diverse queries

Test breadth and depth. Vary card names, games, modes, endpoints, and output formats. **Note wall-clock time** for each request.

#### 3a. Stable baseline queries (test every run)

These provide a regression baseline. Test all of them, every time, so results are comparable across runs.

```bash
BASE=http://localhost:8001

# --- Magic: The Gathering ---

# Baseline M1: iconic card, substitute mode (functional replacements)
curl -s "$BASE/v1/cards/Lightning Bolt/similar?game=magic&mode=substitute&k=10" | python3 -m json.tool

# Baseline M2: multi-word card name, synergy mode (co-occurrence partners)
curl -s "$BASE/v1/cards/Atraxa, Praetors' Voice/similar?game=magic&mode=synergy&k=10" | python3 -m json.tool

# Baseline M3: search query (hybrid text + vector)
curl -s "$BASE/v1/search?game=magic&q=destroy+all+creatures&limit=10" | python3 -m json.tool

# --- Pokemon TCG ---

# Baseline P1: trainer staple, synergy mode (high co-occurrence)
curl -s "$BASE/v1/cards/Professor's Research/similar?game=pokemon&mode=synergy&k=10" | python3 -m json.tool

# Baseline P2: item card, substitute mode
curl -s "$BASE/v1/cards/Ultra Ball/similar?game=pokemon&mode=substitute&k=10" | python3 -m json.tool

# --- Yu-Gi-Oh! ---

# Baseline Y1: iconic card, synergy mode
curl -s "$BASE/v1/cards/Dark Magician/similar?game=yugioh&mode=synergy&k=10" | python3 -m json.tool

# Baseline Y2: archetype member, synergy mode
curl -s "$BASE/v1/cards/Blue-Eyes White Dragon/similar?game=yugioh&mode=synergy&k=10" | python3 -m json.tool

# Baseline Y3: competitive hand trap, synergy mode (modern meta)
curl -s "$BASE/v1/cards/Ash Blossom %26 Joyous Spring/similar?game=yugioh&mode=synergy&k=10" | python3 -m json.tool
```

Record exact top-5 results for each baseline. When comparing against previous runs, diff these first.

**Response schema note**: results use `card` and `similarity` fields (NOT `name`/`score`).

**Verify card metadata in responses**: each result should include a `metadata` object with game-appropriate fields only. The API uses `_BASE_FIELDS` (universal) + `_GAME_BASE_FIELDS` (per-game core) + `_GAME_EXTRA_FIELDS` (per-game extended):
- All games (universal): `image_url`, `type`, `oracle_text` (truncated to 300 chars), `rarity`, `keywords`
- Magic base: `mana_cost`, `cmc`, `colors`, `power`, `toughness`
- Magic extra: `color_identity_str`, `keyword_abilities`, `creature_types`
- Pokemon extra: `hp`, `retreat_cost`, `weakness_type`, `supertype`, `subtypes`, `set_name`, `regulation_mark`
- YGO base: `attribute`, `race`
- YGO extra: `atk`, `def_stat`, `level_rank_link`, `archetype`, `summoning_requirements`, `effect_types`, `name_jp`, `fandom_categories`, `fusion_material`, `synchro_material`, `fandom_statuses`

**Game-specific metadata filtering** (fixed `b74aafd`): verify that cross-game fields are NOT shown:
- `cmc`, `power`, `toughness`, `mana_cost` must NOT appear in Pokemon or YGO results
- `hp`, `retreat_cost` must NOT appear in Magic or YGO results
- Pokemon Trainer cards must NOT show `hp: 0` or `retreat_cost: 0` (suppressed when `supertype == "Trainer"`)
- Check both the expanded stats grid and the card drawer

#### 3b. Rotating exploration queries (pick at least 5, vary each run)

- An obscure / low-play-rate card from each game
- A card with special characters in its name (commas, apostrophes, hyphens)
- A card that exists in multiple printings / variants
- A generic effect query via search ("draw two cards", "deal 3 damage")
- A cross-mode comparison: same card in substitute vs synergy vs meta mode
- A card name that could be ambiguous across games (if any)

#### 3c. Endpoint coverage (test every route)

```bash
BASE=http://localhost:8001

# --- Core similarity ---

# POST /v1/similar (full request body with weights)
curl -s -X POST "$BASE/v1/similar" \
  -H "Content-Type: application/json" \
  -d '{"query":"Lightning Bolt","game":"magic","top_k":10,"mode":"fusion"}' \
  | python3 -m json.tool

# POST /v1/similar with custom fusion weights
curl -s -X POST "$BASE/v1/similar" \
  -H "Content-Type: application/json" \
  -d '{"query":"Lightning Bolt","game":"magic","top_k":10,"mode":"fusion","weights":{"embed":0.5,"jaccard":0.3,"text_embed":0.2}}' \
  | python3 -m json.tool

# GET /v1/cards/{name}/similar (convenience)
curl -s "$BASE/v1/cards/Lightning Bolt/similar?game=magic&k=5" | python3 -m json.tool

# --- Contextual suggestions ---

# GET /v1/cards/{card}/contextual
curl -s "$BASE/v1/cards/Lightning Bolt/contextual?game=magic&top_k=5" | python3 -m json.tool

# --- Search ---

# POST /v1/search
curl -s -X POST "$BASE/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"draw cards","game":"magic","limit":10,"text_weight":0.5,"vector_weight":0.5}' \
  | python3 -m json.tool

# GET /v1/search
curl -s "$BASE/v1/search?game=magic&q=draw+cards&limit=10" | python3 -m json.tool

# --- Card listing ---

# GET /v1/cards (autocomplete / prefix search)
curl -s "$BASE/v1/cards?game=magic&prefix=Light&limit=10" | python3 -m json.tool
curl -s "$BASE/v1/cards?game=magic&limit=5&offset=0" | python3 -m json.tool
curl -s "$BASE/v1/cards?game=magic&limit=5&offset=5" | python3 -m json.tool

# --- Deck operations ---

# POST /v1/deck/suggest_actions
curl -s -X POST "$BASE/v1/deck/suggest_actions" \
  -H "Content-Type: application/json" \
  -d '{"game":"magic","deck":{"Main":["Lightning Bolt","Mountain","Goblin Guide"]}}' \
  | python3 -m json.tool

# POST /v1/deck/complete
# Verify multi-copy: completed deck should have cards with count > 1 (4x MTG, 3x YGO)
curl -s -X POST "$BASE/v1/deck/complete" \
  -H "Content-Type: application/json" \
  -d '{"game":"magic","deck":{"Main":["Lightning Bolt","Mountain","Goblin Guide"]},"target_main_size":60}' \
  | python3 -m json.tool

# POST /v1/deck/apply_patch
curl -s -X POST "$BASE/v1/deck/apply_patch" \
  -H "Content-Type: application/json" \
  -d '{"game":"magic","deck":{"Main":["Lightning Bolt","Mountain"]},"patch":{"ops":[{"op":"add_card","partition":"Main","card":"Goblin Guide","count":1},{"op":"remove_card","partition":"Main","card":"Mountain","count":1}]}}' \
  | python3 -m json.tool

# --- Feedback ---

# POST /v1/feedback
curl -s -X POST "$BASE/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{"query_card":"Lightning Bolt","suggested_card":"Chain Lightning","game":"magic","task_type":"substitution","rating":4,"feedback_text":"correct substitute"}' \
  | python3 -m json.tool
```

#### 3d. Mode and aggregator diversity

```bash
BASE=http://localhost:8001
CARD="Lightning Bolt"

# All use_case modes on same card
for MODE in substitute synergy meta fusion embedding jaccard; do
  echo "=== $MODE ==="
  curl -s "$BASE/v1/cards/$CARD/similar?game=magic&mode=$MODE&k=5" | python3 -m json.tool
done

# Fusion with different weight configurations
# Embedding-heavy
curl -s -X POST "$BASE/v1/similar" \
  -H "Content-Type: application/json" \
  -d '{"query":"Lightning Bolt","game":"magic","top_k":5,"mode":"fusion","weights":{"embed":0.9,"jaccard":0.1}}' \
  | python3 -m json.tool

# Co-occurrence-heavy
curl -s -X POST "$BASE/v1/similar" \
  -H "Content-Type: application/json" \
  -d '{"query":"Lightning Bolt","game":"magic","top_k":5,"mode":"fusion","weights":{"embed":0.1,"jaccard":0.9}}' \
  | python3 -m json.tool

# MMR diversity sweep
for LAMBDA in 0.0 0.5 1.0; do
  echo "=== mmr_lambda=$LAMBDA ==="
  curl -s -X POST "$BASE/v1/similar" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"Lightning Bolt\",\"game\":\"magic\",\"top_k\":10,\"mmr_lambda\":$LAMBDA}" \
    | python3 -m json.tool
done
```

Compare: do different modes actually return different results? Does MMR=0.0 (max diversity) differ visibly from MMR=1.0 (pure relevance)?

#### 3e. CLI coverage

```bash
DECKSAGE="uv run src/ml/cli/main.py"

# Health and readiness
$DECKSAGE health --output json
$DECKSAGE ready --output json

# Similar (all output formats)
$DECKSAGE --game magic similar "Lightning Bolt" --k 5 --output json
$DECKSAGE --game magic similar "Lightning Bolt" --k 5 --output table
$DECKSAGE --game magic similar "Lightning Bolt" --k 5 --output simple

# Search
$DECKSAGE --game magic search "draw cards" --limit 5

# List
$DECKSAGE --game magic list --prefix "Light" --limit 5

# Cross-game
$DECKSAGE --game pokemon similar "Pikachu V" --k 5
$DECKSAGE --game yugioh similar "Dark Magician" --k 5

# Direct mode (bypasses HTTP, uses imports)
$DECKSAGE --direct --game magic similar "Lightning Bolt" --k 5 --output json
```

#### 3f. Multi-game isolation test

Verify that games don't leak into each other:

```bash
BASE=http://localhost:8001

# A Magic card should not appear in Pokemon results
curl -s "$BASE/v1/cards/Lightning Bolt/similar?game=pokemon&k=10" | python3 -m json.tool
# Expected: 404 or empty results (Lightning Bolt is not a Pokemon card)

# A Pokemon card should not appear in Magic results
curl -s "$BASE/v1/cards/Professor's Research/similar?game=magic&k=10" | python3 -m json.tool
# Expected: 404 or empty results

# A YGO card should not appear in Magic results
curl -s "$BASE/v1/cards/Ash Blossom %26 Joyous Spring/similar?game=magic&k=10" | python3 -m json.tool
# Expected: 404 or empty results

# Same search query across games should return game-appropriate results
curl -s "$BASE/v1/search?game=magic&q=fire+damage&limit=5" | python3 -m json.tool
curl -s "$BASE/v1/search?game=pokemon&q=fire+damage&limit=5" | python3 -m json.tool
curl -s "$BASE/v1/search?game=yugioh&q=fire+damage&limit=5" | python3 -m json.tool
```

**Known issue**: Embedding similarity can return cross-game results because the embedding space was trained on multi-game corpus. If a card from game A appears in results for game B, that's a cross-game leakage bug (check `_similar_embedding` filtering).

#### 3g. Error-path testing

These should produce clear errors, not silent failures or 500s:

```bash
BASE=http://localhost:8001

# Unknown card
curl -s -w "\n%{http_code}" "$BASE/v1/cards/ZZZZNOTACARD/similar?game=magic&k=5"

# Invalid game
curl -s -w "\n%{http_code}" "$BASE/v1/cards/Lightning Bolt/similar?game=notreal&k=5"

# k out of range
curl -s -w "\n%{http_code}" "$BASE/v1/cards/Lightning Bolt/similar?game=magic&k=0"
curl -s -w "\n%{http_code}" "$BASE/v1/cards/Lightning Bolt/similar?game=magic&k=999"

# Missing required fields
curl -s -w "\n%{http_code}" -X POST "$BASE/v1/similar" \
  -H "Content-Type: application/json" -d '{}'

# Invalid JSON
curl -s -w "\n%{http_code}" -X POST "$BASE/v1/similar" \
  -H "Content-Type: application/json" -d 'not json'

# Invalid mode
curl -s -w "\n%{http_code}" "$BASE/v1/cards/Lightning Bolt/similar?game=magic&mode=invalid"

# Empty search query
curl -s -w "\n%{http_code}" "$BASE/v1/search?game=magic&q=&limit=5"

# Negative offset
curl -s -w "\n%{http_code}" "$BASE/v1/cards?game=magic&offset=-1"

# Deck operations with empty deck
curl -s -w "\n%{http_code}" -X POST "$BASE/v1/deck/complete" \
  -H "Content-Type: application/json" -d '{"game":"magic","deck":{"Main":[]},"target_main_size":60}'
```

Read the full output of each command. Do not truncate or pipe through head/tail.

### 4. Critique the output

For each query, check:

**Result relevance** (the core question)
- Are the top-5 results actually similar to the query card?
- For substitute mode: are these functional replacements (same mana cost / effect)?
- For synergy mode: are these cards that would go in the same deck?
- For meta mode: are these cards that commonly appear together competitively?
- Does each result include `metadata.image_url`? (CDN URLs from Scryfall, Pokemon TCG API, YGOProDeck)

**Result diversity**
- Does MMR actually diversify results? Or are top-10 all slight variants?
- Are results from multiple archetypes / strategies, or clustered?

**Ranking quality**
- Is the #1 result the most obvious answer? (e.g., Chain Lightning for Lightning Bolt substitutes)
- Does ranking degrade gracefully (top-3 great, top-10 reasonable)?

**Search quality**
- Do search results match the query semantically, not just keyword overlap?
- Does hybrid weighting (text_weight vs vector_weight) actually change results?
- Default search method should be `embedding` (not `fusion` which produces ~1% scores)

**Cross-game isolation**
- Magic queries return only Magic cards?
- No game leakage in any endpoint?

**Contextual suggestions**
- Are synergies, alternatives, upgrades, and downgrades distinct categories?
- Do they make game-mechanical sense?

**Deck operations**
- Does deck completion suggest plausible additions?
- Does deck completion use multi-copy logic? (should see 4x copies for MTG/Pokemon, 3x for YGO, unlimited for basic lands/energy)
- Does suggest_actions give coherent strategy advice?
- Does apply_patch return the expected modified list?

**Latency**
- API response times: P50 and P99 (estimate from wall-clock)
- Any endpoints unreasonably slow (>5s)?

**Output format correctness**
- Does JSON parse cleanly? (`python3 -m json.tool` succeeds)
- Does CLI table output align properly?
- Are card names preserved exactly (no truncation, encoding issues)?

**Error behavior**
- Do bad inputs return 4xx with clear error messages?
- Do any inputs cause 500s?
- Are validation error messages actionable (which field, what constraint)?

### 4b. Player/user experience evaluation (UX)

Open the frontend (`http://localhost:8001/`) in a browser and evaluate it as a real TCG player would. Use the Playwright MCP tools (browser_navigate, browser_snapshot, browser_click, etc.) to interact with the UI.

**Think like a player building a deck.** For each game, simulate a realistic session:

```
Scenarios to test:
1. "I just pulled a Lightning Bolt, what goes with it?" -> search, click contextual
2. "I need a budget replacement for Jace" -> substitute search with budget filter
3. "Build me a Blue-Eyes deck from scratch" -> deck completion flow
4. "My Pikachu V deck needs more draw power" -> suggest_actions flow
```

**First impressions**
- Does the page load quickly? Is there a loading state or does it feel broken?
- Is the search bar obvious? Can a new user figure out what to type?
- Are game selector and mode selector discoverable?

**Theme assessment** (check each game)
- **Magic**: Dark purple-slate bg, gold (#c8a84b) accents, Cinzel serif card names, radial gradient
- **Pokemon**: Light cream bg (#faf6f0), Pokeball red (#cc0000), Outfit rounded sans-serif, yellow card borders, 16px rounded corners, uppercase headers
- **Yu-Gi-Oh**: Dark navy bg (#0a0a18), millennium gold (#c9a84c) accents, Rajdhani uppercase headers, Crimson Pro card names, angular borders

**Search UX**
- Type a partial card name -- does autocomplete feel responsive (<200ms)?
- Type a natural language query ("cards that draw") -- does the mode switch make sense?
- When MeiliSearch is down, does the fallback work or does the user see a cryptic error?
- Do results load with skeleton/shimmer loading state, or does the page feel frozen?

**Results presentation**
- Are card images shown? Are they the right size (150x210px) and loading from CDN?
- Is there an SVG fallback icon for cards without images?
- Is the similarity score meaningful to a player, or just a confusing number?
- Are substitutability badges rendering with game-appropriate colors?
- Does the query card banner show above results with correct metadata (type, stats, image)?
- Can the user tell WHY a card was recommended (reasoning text)?
- Do results feel "right" to a TCG player? Would you actually put these cards in a deck?

**Contextual suggestions**
- Are synergy/alternative/upgrade/downgrade categories clear?
- Do the labels make sense to someone who plays the game?
- Are zero-score results filtered out, or do they clutter the UI?

**Deck building flow**
- Can the user start from scratch and build a coherent deck?
- Is the completion flow discoverable (how do you get to it)?
- Does the completed deck make game-mechanical sense (mana curve, card types)?
- Can the user modify the completed deck (add/remove cards)?

**Pain points to look for**
- Confusing jargon that only ML engineers would understand
- Actions that require multiple clicks when one would do
- Missing feedback (did my action work? is something loading?)
- Results that would make a TCG player laugh or lose trust
- Mobile responsiveness (resize browser to 375px width and check stacked layout)

**Competitive player perspective**
- Would a competitive Magic/YGO/Pokemon player trust these recommendations?
- Are meta-relevant cards showing up, or only casual/kitchen-table cards?
- Does the system understand archetype identity (burn vs control vs midrange)?

### 4c. Visual quality evaluation (VLM critique)

Take Playwright screenshots of each game theme with search results loaded, then run the automated VLM critique.

**Screenshot procedure** (via Playwright MCP tools):

1. Navigate to `http://localhost:8001/`
2. For each game (Magic, Pokemon, Yu-Gi-Oh!):
   a. Select the game radio button (`.game-btn[data-game="X"]`)
   b. Search for a representative card (Lightning Bolt / Professor's Research / Ash Blossom & Joyous Spring)
   c. Wait for results to load (including card images from CDN)
   d. **Close autocomplete dropdown** -- press Escape key. The dropdown overlays results and ruins screenshots.
   e. Wait 1-2s for card images to finish loading from CDN
   f. Scroll to show results area (scroll ~350px down so query banner + top results visible)
   g. Take viewport screenshot to `/tmp/vlm_{magic,pokemon,yugioh}.png`

**Important**: The game selector uses radio buttons with `input[name="game"]`, not a `#searchGame` select element. Click the `.game-btn[data-game="pokemon"]` div, not the radio input directly.

**Run VLM critique**:

```bash
# Requires GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY in env
DISABLE_LLM_CACHE=true node scripts/vlm_critique.mjs
```

This evaluates each theme on 7 card-game-specific dimensions using a VLM with a custom rubric:

| Dimension | What it measures |
|-----------|-----------------|
| game_authenticity | Brand match to official game websites/apps |
| visual_hierarchy | Card image prominence, score readability, metadata scannability |
| typography | Font choice appropriateness, sizing hierarchy, readability |
| spacing_layout | Whitespace balance, card density, breathing room |
| color_harmony | Palette cohesion, contrast ratios, text legibility |
| card_presentation | Image framing, border treatment, hover effects |
| modern_polish | Transitions, shadow depth, production quality |

**Pass threshold**: 7/10 per theme. Script exits non-zero if any theme fails.

**What to check in the output**:
- Are all 3 themes scoring >= 7/10? Note specific dimension failures if not.
- Are dimensionScores structured (JSON object) or only in reasoning text?
- Which dimensions are weakest across themes? (common: spacing_layout)
- Top actionable CSS fix from each theme's recommendations

**If a theme fails**:
1. Read the VLM's per-dimension scores and top-3 CSS recommendations
2. Apply the highest-impact fix (usually one CSS property change)
3. Re-screenshot and re-run `vlm_critique.mjs` on that theme only
4. Iterate until >= 7/10

**Cache note**: The VLM cache is content-addressed (SHA-256 of image bytes). Re-screenshotting to the same `/tmp/vlm_*.png` path automatically invalidates stale cache entries. Use `DISABLE_LLM_CACHE=true` to bypass cache entirely, or `--clear` to wipe it.

**Record in report**: Per-theme overall score, per-dimension breakdown, and the top actionable fix from each critique.

### 4d. Run E2E test suite

Run the automated Playwright tests as a regression gate:

```bash
npx playwright test --reporter=list
```

All 45 tests should pass (42 functional + 3 VLM screenshot tests). The VLM visual quality tests verify each theme >= 7/10.

If tests fail, investigate and fix before writing the report. Common failure causes:
- **Card drawer tests**: `openCardDrawer()` uses `document.querySelector('input[name="game"]:checked')` for game detection. If the game variable is wrong or undefined, the function throws a ReferenceError silently and the drawer never opens.
- **Autocomplete tests**: timing-sensitive. The autocomplete dropdown needs MeiliSearch running.
- **Screenshot tests**: need CDN-loaded card images. Wait for `networkidle` before screenshotting.

Record pass/fail counts in the report.

### 5. Write the report

Save to `qa/reports/qa-YYYY-MM-DD.md`. Produce a structured critique covering:

1. **Test conditions**: date, API version, card counts per game, embedding dimensions, wall-clock timings, port used
2. **Baseline results**: exact top-5 for each stable baseline (section 3a), diffed against previous run if available
3. **Card metadata**: verify `image_url` and `oracle_text` present in SimilarCard responses for all 3 games
4. **Per-game findings**: which game has strongest results, weakest, any game-specific issues
5. **Mode comparison**: how do substitute / synergy / meta / fusion differ in practice?
6. **Endpoint coverage**: which endpoints worked, which errored, which produced surprising output
7. **Deck operations assessment**: quality of completions (verify multi-copy: cards should have count > 1), suggestions, patches
8. **Error handling**: which error-path tests produced good messages vs bad ones
9. **Latency profile**: per-endpoint timing observations
10. **Player/UX experience**: frontend usability, search feel, result trust, pain points, theme assessment (from section 4b)
11. **Visual quality**: per-theme VLM scores with dimension breakdowns (from section 4c)

    | Theme | Score | Auth | Hier | Typo | Space | Color | Card | Polish |
    |-------|-------|------|------|------|-------|-------|------|--------|
    | Magic | ?/10  |      |      |      |       |       |      |        |
    | Pokemon | ?/10 |     |      |      |       |       |      |        |
    | Yu-Gi-Oh | ?/10 |    |      |      |       |       |      |        |

12. **E2E test results**: pass/fail count from `npx playwright test`, note any failures
13. **Overall assessment**: strengths, weaknesses, surprises
14. **Actionable issues**: specific things worth fixing, ordered by impact (include API, UX, and visual issues)

Be concrete. Quote card names, show expected vs actual results, include the curl command that reproduces each issue.

### 6. Regression check on known bugs

Check whether these previously-identified issues are still present (update this list as bugs are fixed or new ones found):

#### Fixed (23 issues resolved)

MMR lambda no-effect and falsy-check bugs, suggest_actions/apply_patch deck format normalization, contextual endpoint latency (fast-only modalities), Pokemon zero-scored synergies, frontend JS parse error and /sw.js 404, YGO/Pokemon deck "Main" key normalization, meta mode using jaccard (was fusion/67s), zero-score contextual synergy filtering, search 503 on backend errors, non-English card names in deck completion (v4 embeddings), YGO synergy returning empty results (wrong pairs file), card drawer ReferenceError (currentGame undefined), Pokemon Trainer cards showing HP 0/Retreat 0 (`b74aafd`), cross-game metadata leaking into expanded panel (`b74aafd`, `_GAME_BASE_FIELDS` split), cross-game metadata leaking into card drawer (`b74aafd`), CSV card names with leading whitespace, `[object Object]` rendering in nested metadata, deck completion always adding 1x copy (`b74aafd`, now fills to game copy limit), thread safety in `_build_deck_hooks` (`323c70b`), score clamping and boundary validation (`323c70b`), DeckRefiner 682 LOC redundant module removed (`19f3b2d`). See git history for details.

#### Open

- [ ] Contextual endpoint returning empty upgrades/downgrades for all games
- [ ] Deck completion suggesting cards not in the game's card pool (cross-game leakage in embedding results)
- [ ] Pagination (offset) not working correctly on /v1/cards
- [ ] Mode parameter silently falling back to default when invalid (should 400)
- [ ] Direct mode (--direct) returning different results than HTTP mode
- [ ] MeiliSearch not configured with filterable attributes, synonyms, or ranking rules
- [ ] Qdrant not using payload indexing or multi-vector support
- [ ] Visual embeddings stored in Qdrant payload instead of named vectors
- [ ] Feedback rating range documentation (max is 4, not 5)
- [ ] No color identity filtering for Magic deck completion
- [ ] Pikachu V not in Pokemon embedding vocab (rotated out of competitive play -- data coverage gap)
- [ ] Dark Magician synergy returns Red-Eyes cards (cross-archetype bleed via Red-Eyes Dark Dragoon shared support -- not wrong, but unexpected)
- [ ] MMR lambda 0.0 vs 0.5 producing identical results (flat similarity space, not a code bug)
- [ ] Fusion mode ~65s latency (functionally unusable -- iterates all cards twice)
- [ ] Cross-game leakage: embedding similarity returns results from wrong game pool for some cards

### 7. Compare against previous runs

Read previous reports from `qa/reports/`. For each:
- Are baseline top-5 results identical, improved, or regressed?
- Are bugs from section 6 still present?
- Any new bugs not seen before?
- Any previous bugs now fixed (update the checklist)?
- Have VLM visual scores changed? (compare dimension breakdowns)

### 8. Teardown

```bash
kill $API_PID 2>/dev/null
```

## What this is NOT

- Not a metric evaluation against gold labels (that's `just eval-runctl-local` with annotated test sets)
- Not a unit test suite (that's `just test`)
- Not an architecture validation (that's `just check-architecture`)
- Not an E2E browser test (that's `just test-e2e`)

This answers: "if someone queried DeckSage for card recommendations, would the results be useful, and does the UI do them justice?"
