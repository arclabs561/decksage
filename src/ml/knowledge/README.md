# Game Knowledge Injection System

Dynamic game knowledge injection for LLM prompts using RAG (Retrieval-Augmented Generation).

## Overview

This system injects game-specific knowledge (mechanics, archetypes, formats, examples) into LLM prompts to improve accuracy and reduce cross-game contamination.

## Architecture

- **Pydantic Models** (`models.py`): Structured knowledge representation
- **Knowledge Base** (`game_knowledge_base.py`): RAG retrieval system
- **Knowledge Files** (`data/game_knowledge/*.json`): Game-specific knowledge

## Usage

### Basic Usage

```python
from ml.knowledge import retrieve_game_knowledge

# Retrieve knowledge for a query
knowledge = retrieve_game_knowledge(
    game="magic",
    query="Lightning Bolt",
    format="Modern",
    archetype="Burn",
)

# Inject into prompt
prompt = f"""
{base_prompt}

**Game Mechanics:**
{knowledge['mechanics']}

**Relevant Archetypes:**
{knowledge['archetypes']}
"""
```

### Advanced Usage

```python
from ml.knowledge import GameKnowledgeBase

kb = GameKnowledgeBase()
knowledge = kb.retrieve_relevant_knowledge(
    game="magic",
    query="Lightning Bolt vs Chain Lightning",
    format="Legacy",
    top_k=5,
)
```

## Knowledge File Structure

Knowledge files are JSON following the `GameKnowledge` Pydantic model:

```json
{
  "game": "magic",
  "mechanics": {
    "mana_system": "...",
    "color_system": "...",
    "card_types": [...],
    "keywords": [...]
  },
  "archetypes": [
    {
      "name": "Burn",
      "description": "...",
      "strategy": "...",
      "core_cards": [...],
      "flex_slots": [...]
    }
  ],
  "formats": [
    {
      "name": "Modern",
      "legal_sets": [...],
      "ban_list": [...],
      "meta_context": "..."
    }
  ],
  "examples": [
    {
      "query": "Lightning Bolt",
      "card1": "Lightning Bolt",
      "card2": "Chain Lightning",
      "score": 0.92,
      "reasoning": "..."
    }
  ]
}
```

## Validation

Validate knowledge files:

```bash
python -m ml.knowledge.validate_knowledge
```

## Integration Points

Knowledge injection is integrated into:

1. **LLM Annotator** (`src/ml/annotation/llm_annotator.py`): Injects knowledge into similarity annotation prompts
2. **Label Generation** (`src/ml/scripts/generate_labels_enhanced.py`): Injects knowledge into label generation prompts

## Testing

Run tests:

```bash
pytest tests/test_game_knowledge_injection.py -v
pytest tests/test_knowledge_integration.py -v
```

## Adding New Games

1. Create `data/game_knowledge/{game}.json` following the schema
2. Validate: `python -m ml.knowledge.validate_knowledge`
3. Test retrieval for the new game

## Future Enhancements

- Embedding-based semantic search (currently keyword-based)
- Vector store for faster retrieval at scale
- Automatic knowledge updates from external sources
- Temporal context tracking (ban list changes, meta shifts)

