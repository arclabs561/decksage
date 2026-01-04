# Shared Utilities for Multi-Game Experiments

Abstracts common patterns from 39+ experiments across Magic, Yu-Gi-Oh!, and Pokemon.

## Module Organization

- **`paths.py`**: Canonical paths for data, embeddings, test sets
- **`data_loading.py`**: Load pairs, embeddings, test sets with game filtering
- **`evaluation.py`**: Core evaluation metrics (P@K, MRR, NDCG) - standard version
- **`evaluation_with_ci.py`**: Evaluation with confidence intervals - use for rigorous analysis
- **`constants.py`**: Game-specific filters and relevance weights
- **`annotation_utils.py`**: Load and convert annotations (similarity → substitution pairs)
- **`pydantic_ai_helpers.py`**: Shared utilities for Pydantic AI agents
- **`llm_cost_tracker.py`**: Track LLM API costs
- **`llm_cache.py`**: Cache LLM responses
- **`name_normalizer.py`**: Card name normalization
- **`aim_helpers.py`**: AimStack experiment tracking (optional)

## Usage

### Loading Data

```python
from utils import PATHS, load_pairs, load_embeddings, load_test_set

# Load pairs with game-specific filtering
df = load_pairs(
    dataset='large',           # or '500' or custom path
    game='magic',              # 'magic', 'yugioh', 'pokemon'
    filter_common=True,        # Remove lands/energy/staples
    filter_level='basic'       # 'basic', 'common', 'all'
)

# Load embeddings
wv = load_embeddings('magic_39k_decks_pecanpy')

# Load test set
test_set = load_test_set(game='magic')  # or 'yugioh', 'pokemon'

# Load and convert annotations
from utils.annotation_utils import (
    load_similarity_annotations,
    extract_substitution_pairs_from_annotations,
    convert_annotations_to_substitution_pairs,
)

# Load similarity annotations
annotations = load_similarity_annotations(Path("annotations/similarity_annotations.jsonl"))

# Extract substitution pairs for training
substitution_pairs = extract_substitution_pairs_from_annotations(
    annotations,
    min_similarity=0.8,
    require_substitute_flag=True,
)
```

### Building Graph

```python
from utils import build_adjacency_dict, get_filter_set

# Build adjacency with filtering
filter_set = get_filter_set('magic', 'common')
adj = build_adjacency_dict(df, filter_set=filter_set)
```

### Evaluation

```python
from utils import evaluate_similarity, jaccard_similarity

# Define similarity function
def my_similarity(query: str, k: int):
    neighbors = adj[query]
    sims = []
    for other in adj.keys():
        if other != query:
            sim = jaccard_similarity(neighbors, adj[other])
            sims.append((other, sim))
    sims.sort(key=lambda x: x[1], reverse=True)
    return sims[:k]

# Evaluate
results = evaluate_similarity(
    test_set=test_set,
    similarity_func=my_similarity,
    top_k=10,
    verbose=True
)

print(f"P@10: {results['p@10']:.4f}")
```

### Constants

```python
from utils import GAME_FILTERS, get_filter_set

# Get filter sets
magic_basic = get_filter_set('magic', 'basic')  # Basic lands
magic_all = get_filter_set('magic', 'all')      # All common cards
pokemon_energy = get_filter_set('pokemon', 'basic')
```

### Paths

```python
from utils import PATHS

# Access canonical paths
pairs = PATHS.pairs_large
embeddings_dir = PATHS.embeddings
test_set = PATHS.test_magic

# Dynamic paths
embedding_path = PATHS.embedding('my_model')
graph_path = PATHS.graph('my_graph')
```

## Migration Guide

### Before (run_exp_033.py example):

```python
LANDS = {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'}
df = pd.read_csv('../backend/pairs_large.csv')

adj = defaultdict(set)
for _, row in df.iterrows():
    c1, c2 = row['NAME_1'], row['NAME_2']
    if c1 not in LANDS and c2 not in LANDS:
        adj[c1].add(c2)
        adj[c2].add(c1)

with open('../../experiments/test_set_canonical_magic.json') as f:
    test_set = json.load(f)
```

### After:

```python
from utils import load_pairs, build_adjacency_dict, load_test_set, get_filter_set

df = load_pairs('large', game='magic', filter_common=True)
filter_set = get_filter_set('magic', 'basic')
adj = build_adjacency_dict(df, filter_set=filter_set)
test_set = load_test_set('magic')
```

## Multi-Game Support

Each game has its own filter configuration:

- **Magic**: Basic lands, snow-covered variants, common staples
- **Yu-Gi-Oh!**: Common staples (currently minimal)
- **Pokemon**: Basic energy cards, special energy

Extend `GAME_FILTERS` in `constants.py` for new games or additional filters.

## Design Principles

1. **Game-agnostic by default** - Works for any card game
2. **Flexible filtering** - Per-game customization when needed
3. **Canonical paths** - Single source of truth for file locations
4. **Consistent evaluation** - Same metrics across all games
5. **Easy migration** - Drop-in replacement for existing code

## Testing

See `tests/` directory for unit tests covering:
- Data loading consistency
- Evaluation metric correctness
- Path resolution
- Multi-game filtering


