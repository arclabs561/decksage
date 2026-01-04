# GitHub Repository Topics

## Recommended Topics (Priority Order)

### High Priority (Core Identity)
1. `python` - Primary language
2. `go` - Backend language
3. `machine-learning` - Core purpose
4. `graph-neural-networks` - Key ML technique
5. `trading-card-games` - Domain

### Medium Priority (Techniques)
6. `embeddings` - Core ML approach
7. `similarity-search` - Main use case
8. `node2vec` - Specific algorithm
9. `deck-building` - Application domain

### Lower Priority (Specific Games - choose 1-2)
10. `magic-the-gathering` - Primary game
11. `pokemon-tcg` - Secondary game

### Optional (Infrastructure)
- `fastapi` - API framework
- `pytorch` - ML framework
- `sqlite` - Database

## Description
Card similarity search using tournament deck co-occurrence, graph embeddings, and hybrid ML models for trading card games.

## Why These Topics?

1. **python** + **go**: Clear technology stack
2. **machine-learning** + **graph-neural-networks**: Core ML approach
3. **trading-card-games**: Domain specificity
4. **embeddings** + **similarity-search**: Use case clarity
5. **deck-building**: Application focus

## Implementation

```bash
# Set description
gh repo edit --description "Card similarity search using tournament deck co-occurrence, graph embeddings, and hybrid ML models for trading card games"

# Add topics
gh repo edit --add-topic python --add-topic go --add-topic machine-learning \
  --add-topic graph-neural-networks --add-topic trading-card-games \
  --add-topic embeddings --add-topic similarity-search --add-topic node2vec \
  --add-topic deck-building --add-topic magic-the-gathering
```
