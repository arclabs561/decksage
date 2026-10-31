import collections
import json
import re
import statistics

from ml.utils.paths import PATHS


ROOT = PATHS.project_root
cards = json.loads((PATHS.data / "raw" / "scryfall" / "oracle-cards.json").read_text())


def norm_text(t):
    t = re.sub(r"\([^)]*\)", "", t or "")
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def norm_type(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


by_text = collections.defaultdict(list)
for c in cards:
    name = c.get("name")
    text = norm_text(c.get("oracle_text") or "")
    if not name or not text or len(text) < 10:
        continue
    by_text[(text, norm_type(c.get("type_line") or ""))].append(
        (name, c.get("mana_cost") or "", c.get("cmc") or 0)
    )
groups = [v for v in by_text.values() if len(v) >= 2]
pairs = sum(len(g) * (len(g) - 1) // 2 for g in groups)
print("groups", len(groups), "pairs", pairs, "cards in groups", sum(len(g) for g in groups))
print("largest", sorted((len(g) for g in groups), reverse=True)[:10])
# label coverage in test set
ts = json.loads((PATHS.data / "test_sets" / "annotated_magic_v2.json").read_text())
judged = {}
for q, o in ts["queries"].items():
    for a in o.get("annotations", []):
        if isinstance(a, dict) and a.get("candidate"):
            judged[frozenset((q, a["candidate"]))] = a.get("functional_score")
covered = 0
scores = []
for g in groups:
    for i in range(len(g)):
        for j in range(i + 1, len(g)):
            s = judged.get(frozenset((g[i][0], g[j][0])))
            if isinstance(s, (int, float)):
                covered += 1
                scores.append(s)
print(
    "reprint pairs with a judged label",
    covered,
    "mean functional",
    round(statistics.mean(scores), 3) if scores else None,
)
# embedding recall of co-members
from gensim.models import KeyedVectors


kv = KeyedVectors.load(str(PATHS.embeddings / "magic_v7_spectral_mu35.wv"))
recall10 = []
recall50 = []
ranks = []
for g in groups:
    names = [x[0] for x in g if x[0] in kv]
    if len(names) < 2:
        continue
    for name in names:
        others = set(names) - {name}
        sims = kv.most_similar(name, topn=50)
        pos = {n: i + 1 for i, (n, _) in enumerate(sims)}
        hits = [pos[o] for o in others if o in pos]
        if not hits:
            ranks.append(51)
            recall10.append(0)
            recall50.append(0)
            continue
        best = min(hits)
        ranks.append(best)
        recall10.append(1 if best <= 10 else 0)
        recall50.append(1 if best <= 50 else 0)
print(
    "queries",
    len(ranks),
    "recall@10",
    round(statistics.mean(recall10), 4) if recall10 else None,
    "recall@50",
    round(statistics.mean(recall50), 4) if recall50 else None,
    "median rank",
    statistics.median(ranks) if ranks else None,
)
json.dump(
    {
        "groups": len(groups),
        "pairs": pairs,
        "cards": sum(len(g) for g in groups),
        "judged_pairs": covered,
        "judged_mean_functional": round(statistics.mean(scores), 4) if scores else None,
        "embedding_queries": len(ranks),
        "recall_at_10": round(statistics.mean(recall10), 4) if recall10 else None,
        "recall_at_50": round(statistics.mean(recall50), 4) if recall50 else None,
        "median_rank": statistics.median(ranks) if ranks else None,
    },
    open(ROOT / "data-local/label-anchor-20261030/reprint_probe.json", "w"),
    indent=2,
)
