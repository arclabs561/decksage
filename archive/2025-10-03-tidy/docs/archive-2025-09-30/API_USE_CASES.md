# API Use Case Examples

## Substitutes (Functional Replacements)

**Question:** "I don't have Lightning Bolt, what can I use?"

```bash
curl -X POST http://localhost:8000/similar \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Lightning Bolt",
    "use_case": "substitute",
    "top_k": 5
  }'
```

**Returns:** Chain Lightning, Lava Spike, Fireblast
**Method:** Node2Vec (learns functional patterns)
**P@10:** 0.50

## Synergies (Cards That Work Together)

**Question:** "What works well WITH Lightning Bolt?"

```bash
curl -X POST http://localhost:8000/similar \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Lightning Bolt",
    "use_case": "synergy",
    "top_k": 5
  }'
```

**Returns:** Monastery Swiftspear, Rift Bolt, Lava Dart
**Method:** Jaccard (direct co-occurrence)
**P@10:** 0.14

## Meta Analysis

**Question:** "What's popular with Orcish Bowmasters?"

```bash
curl -X POST http://localhost:8000/similar \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Orcish Bowmasters",
    "use_case": "meta",
    "top_k": 10
  }'
```

**Returns:** Current tournament pairings
**Method:** Jaccard (temporal weighted)
