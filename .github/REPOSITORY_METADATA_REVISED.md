# GitHub Repository Metadata - Revised Recommendations

## Analysis: What This Repository Actually Does

### Primary Use Cases
1. **Card Similarity Search** - Find functionally similar cards
2. **Budget Substitution** - Find cheaper alternatives to expensive cards
3. **Deck Completion** - Suggest cards to complete a deck
4. **Card Recommendations** - Recommend cards based on context

### Key Features
- Multi-game support (Magic, Pokemon, Yu-Gi-Oh)
- Tournament deck co-occurrence analysis
- Hybrid ML system (GNN + embeddings + co-occurrence)
- Functional tagging (90+ tags across games)
- LLM semantic enrichment

### Technologies
- Python (primary) + Go (backend scraping)
- Graph Neural Networks (GraphSAGE)
- Instruction-tuned embeddings (E5-base-v2)
- Node2Vec/PecanPy for co-occurrence
- FastAPI for REST API

## Revised Topic Recommendations

### Core (Must Have - 5)
1. `python` - Primary language
2. `machine-learning` - Core purpose
3. `graph-neural-networks` - Key ML technique
4. `trading-card-games` - Domain
5. `recommendation-system` - **Primary use case** (not just similarity)

### Domain/Application (Should Have - 3)
6. `deck-building` - Application domain
7. `card-game` - Broader domain (more discoverable than trading-card-games)
8. `similarity-search` - Core functionality

### Technical (Nice to Have - 2)
9. `embeddings` - ML approach
10. `node2vec` - Specific algorithm

### Alternative Considerations
- `budget-substitution` - Too specific, not a common topic
- `magic-the-gathering` - Too game-specific, limits discoverability
- `go` - Secondary language, less important than ML focus
- `pytorch` - Implied by graph-neural-networks
- `fastapi` - Infrastructure, not core identity

## Why These Changes?

1. **recommendation-system** > similarity-search
   - More accurately describes the use case
   - Broader discoverability
   - Covers substitution, completion, recommendations

2. **card-game** > magic-the-gathering
   - More discoverable
   - Covers all games (MTG, Pokemon, YGO)
   - Not limiting to one game

3. **Remove go**
   - Secondary language
   - Not core to repository identity
   - Python + ML is the focus

4. **Keep graph-neural-networks**
   - Key differentiator
   - Specific ML technique
   - High discoverability

## Final Recommended Topics (10)

1. `python`
2. `machine-learning`
3. `graph-neural-networks`
4. `recommendation-system`
5. `trading-card-games`
6. `deck-building`
7. `card-game`
8. `similarity-search`
9. `embeddings`
10. `node2vec`

## Description Options

**Current:**
"Card similarity search using tournament deck co-occurrence, graph embeddings, and hybrid ML models for trading card games"

**Alternative (more accurate):**
"ML-powered card recommendations for trading card games: budget substitutions, deck completion, and similarity search using graph embeddings and tournament deck analysis"

**Shorter:**
"Card recommendations for trading card games using graph neural networks and tournament deck co-occurrence analysis"
