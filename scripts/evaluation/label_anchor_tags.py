import collections
import gzip
import json
import math
import statistics

from ml.utils.paths import PATHS


ROOT = PATHS.project_root
# name -> oracle_id
cards = json.loads((PATHS.data / "raw" / "scryfall" / "oracle-cards.json").read_text())
name_to_oid = {c["name"]: c["oracle_id"] for c in cards if c.get("name") and c.get("oracle_id")}
# oracle_id -> tags
tags = collections.defaultdict(set)
with gzip.open(ROOT / "data-local/label-anchor-20261030/oracle-tags.jsonl.gz", "rt") as f:
    for line in f:
        t = json.loads(line)
        label = t.get("label")
        if not label:
            continue
        for tag in t.get("taggings", []):
            oid = tag.get("oracle_id")
            if oid:
                tags[oid].add(label)
print("cards", len(name_to_oid), "tagged oracle ids", len(tags))
# document frequency for idf
df = collections.Counter()
for s in tags.values():
    for t in s:
        df[t] += 1
N = max(1, len(tags))
idf = {t: math.log((N + 1) / (d + 1)) + 1.0 for t, d in df.items()}


def jaccard(a, b):
    if not a or not b:
        return None
    u = len(a | b)
    return len(a & b) / u if u else None


def wjaccard(a, b):
    if not a or not b:
        return None
    common = a & b
    union = a | b
    den = sum(idf.get(t, 1.0) for t in union)
    return sum(idf.get(t, 1.0) for t in common) / den if den else None


ts = json.loads((PATHS.data / "test_sets" / "annotated_magic_v2.json").read_text())
rows = collections.defaultdict(list)
role_rows = collections.defaultdict(list)
mapped = 0
total = 0
for q, o in ts["queries"].items():
    qoid = name_to_oid.get(q)
    if not qoid:
        continue
    qtags = tags.get(qoid, set())
    for a in o.get("annotations", []):
        if not isinstance(a, dict):
            continue
        s = a.get("functional_score")
        c = a.get("candidate")
        if not isinstance(s, (int, float)) or not isinstance(c, str):
            continue
        total += 1
        coid = name_to_oid.get(c)
        if not coid:
            continue
        mapped += 1
        j = jaccard(qtags, tags.get(coid, set()))
        w = wjaccard(qtags, tags.get(coid, set()))
        if j is not None:
            rows[q].append((float(s), j, w))
        ra, rb = a.get("card_a_role"), a.get("card_b_role")
        if ra and rb:
            role_rows[q].append((float(s), 1.0 if ra == rb else 0.0))


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def corr(x, y):
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return (
        None if sx == 0 or sy == 0 else sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)
    )


def within(data, idx):
    vals = []
    for q, rs in data.items():
        if len(rs) < 5:
            continue
        x = [r[0] for r in rs]
        y = [r[idx] for r in rs]
        r = corr(ranks(x), ranks(y))
        if r is not None:
            vals.append(r)
    if not vals:
        return None
    return {
        "n": len(vals),
        "mean": round(statistics.mean(vals), 4),
        "median": round(statistics.median(vals), 4),
        "positive_share": round(sum(1 for r in vals if r > 0) / len(vals), 4),
    }


print("annotations total", total, "mapped to oracle ids", mapped)
print("tag pairs in queries", sum(len(v) for v in rows.values()))
print("jaccard", within(rows, 1))
print("weighted jaccard", within(rows, 2))
print("role agreement", within(role_rows, 1))
json.dump(
    {
        "total": total,
        "mapped": mapped,
        "tag_pairs": sum(len(v) for v in rows.values()),
        "jaccard": within(rows, 1),
        "weighted_jaccard": within(rows, 2),
        "role_agreement": within(role_rows, 1),
    },
    open(ROOT / "data-local/label-anchor-20261030/anchor.json", "w"),
    indent=2,
)
