#!/usr/bin/env python3
"""Exercise the API the way an agent would and record friction.

Deterministic on purpose: the same calls an agent makes, with shape, status
and latency assertions. Output feeds the API fixes; an LLM is not required to
see a 404 on /health or a two-step deck parse.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx


BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[2] / ".agents" / "reports" / "api-critique.json"


def timed(client: httpx.Client, method: str, path: str, **kwargs):
    started = time.perf_counter()
    response = client.request(method, path, timeout=60, **kwargs)
    elapsed = (time.perf_counter() - started) * 1000
    try:
        body = response.json()
    except Exception:
        body = None
    return response.status_code, body, round(elapsed, 1)


def main() -> int:
    checks = []

    def record(name: str, ok: bool, detail: str, status: int, latency: float):
        checks.append({"check": name, "ok": ok, "detail": detail, "status": status, "ms": latency})

    with httpx.Client(base_url=BASE) as client:
        status, body, ms = timed(client, "GET", "/health")
        record(
            "health alias",
            status == 200 and body and body.get("status") == "live",
            f"GET /health -> {status}",
            status,
            ms,
        )

        status, body, ms = timed(
            client,
            "GET",
            "/v1/cards",
            params={"game": "magic", "prefix": "lightning bolt", "limit": 3},
        )
        first = (body or {}).get("items", [{}])[0].get("name")
        record(
            "autocomplete exact prefix",
            status == 200 and first == "Lightning Bolt",
            f"first={first}",
            status,
            ms,
        )

        status, body, ms = timed(
            client,
            "GET",
            "/v1/cards",
            params={"game": "yugioh", "prefix": "dark magicain", "limit": 3},
        )
        first = (body or {}).get("items", [{}])[0].get("name")
        record(
            "autocomplete typo",
            status == 200 and first == "Dark Magician",
            f"first={first}",
            status,
            ms,
        )

        status, body, ms = timed(
            client,
            "POST",
            "/v1/search",
            json={"game": "magic", "query": "Lightning Bolt", "limit": 1},
        )
        record(
            "search exact signal",
            status == 200 and (body or {}).get("exact_match") is True,
            f"exact_match={(body or {}).get('exact_match')}",
            status,
            ms,
        )

        status, body, ms = timed(
            client,
            "POST",
            "/v1/search",
            json={"game": "magic", "query": "destroy all creatures", "limit": 5},
        )
        names = [r["card_name"] for r in (body or {}).get("results", [])]
        record(
            "effect query survives filters",
            status == 200 and "Day of Judgment" in names,
            f"top={names[:3]}",
            status,
            ms,
        )

        for mode in ("embedding", "text", "union"):
            status, body, ms = timed(
                client,
                "POST",
                "/v1/similar",
                json={"game": "magic", "query": "Lightning Bolt", "top_k": 5, "mode": mode},
            )
            record(
                f"similar mode={mode}",
                status == 200 and len((body or {}).get("results", [])) >= 3,
                f"n={len((body or {}).get('results', []))} method={(body or {}).get('model_info', {}).get('method_used')}",
                status,
                ms,
            )

        status, body, ms = timed(
            client,
            "POST",
            "/v1/similar",
            json={"game": "magic", "query": "lightning bolt", "top_k": 3},
        )
        record(
            "similar lowercase",
            status == 200 and len((body or {}).get("results", [])) >= 1,
            f"n={len((body or {}).get('results', []))}",
            status,
            ms,
        )

        status, body, ms = timed(
            client,
            "POST",
            "/v1/similar",
            json={"game": "magic", "query": "1996 World Champion", "top_k": 3},
        )
        record(
            "catalog-only card is honest",
            status == 200
            and (body or {}).get("exact_match") is True
            and (body or {}).get("model_info", {}).get("no_vector") is True,
            f"exact={(body or {}).get('exact_match')} no_vector={(body or {}).get('model_info', {}).get('no_vector')}",
            status,
            ms,
        )

        status, body, ms = timed(
            client,
            "GET",
            "/v1/graph/neighbors",
            params={
                "game": "magic",
                "card": "Lightning Bolt",
                "relations": "text,tag,cooccurrence",
                "limit": 5,
            },
        )
        relations = {n.get("relation") for n in (body or {}).get("neighbors", [])}
        record(
            "graph typed neighbours",
            status == 200 and (body or {}).get("source") == "unified" and relations,
            f"relations={sorted(relations)}",
            status,
            ms,
        )

        status, body, ms = timed(client, "GET", "/v1/graph/stats", params={"game": "magic"})
        record("graph stats", status == 200, f"GET /v1/graph/stats -> {status}", status, ms)

        status, body, ms = timed(
            client, "GET", "/v1/cards/Lightning%20Bolt", params={"game": "magic"}
        )
        record(
            "card metadata tool",
            status == 200 and (body or {}).get("metadata"),
            f"metadata={bool((body or {}).get('metadata'))}",
            status,
            ms,
        )

        status, body, ms = timed(
            client, "GET", "/v1/cards/Lightning%20Bolt/legality", params={"game": "magic"}
        )
        record(
            "legality tool",
            status == 200 and (body or {}).get("legalities"),
            f"formats={len((body or {}).get('legalities', {}))}",
            status,
            ms,
        )

        deck = {"Main": [{"name": "Lightning Bolt", "count": 4}, {"name": "Mountain", "count": 20}]}
        status, body, ms = timed(
            client,
            "POST",
            "/v1/deck/complete",
            json={
                "game": "magic",
                "deck": deck,
                "target_main_size": 30,
                "max_steps": 5,
                "method": "greedy",
            },
        )
        record(
            "deck complete json",
            status == 200 and (body or {}).get("steps"),
            f"steps={len((body or {}).get('steps', []))}",
            status,
            ms,
        )

        status, body, ms = timed(
            client,
            "POST",
            "/v1/deck/complete",
            json={
                "game": "magic",
                "deck_text": "4 Lightning Bolt\n20 Mountain",
                "target_main_size": 30,
                "max_steps": 5,
                "method": "greedy",
            },
        )
        record(
            "deck complete text (agent ergonomics)",
            status == 200,
            f"text body -> {status}",
            status,
            ms,
        )

        status, body, ms = timed(client, "GET", "/v1/index/status")
        games = (body or {}).get("games", {})
        record(
            "index status", status == 200 and len(games) == 3, f"games={list(games)}", status, ms
        )

        status, body, ms = timed(
            client, "GET", "/v1/cards", params={"game": "mtg", "prefix": "bolt", "limit": 1}
        )
        record(
            "game alias mtg",
            status == 200 and bool((body or {}).get("items")),
            f"GET /v1/cards?game=mtg -> {status}",
            status,
            ms,
        )

        status, body, ms = timed(
            client, "POST", "/v1/search", json={"game": "ygo", "query": "Dark Magician", "limit": 1}
        )
        record(
            "game alias ygo",
            status == 200 and (body or {}).get("exact_match") is True,
            f"exact_match={(body or {}).get('exact_match')}",
            status,
            ms,
        )

        status, body, ms = timed(
            client, "POST", "/v1/search", json={"game": "nope", "query": "x", "limit": 1}
        )
        detail = (body or {}).get("detail")
        record(
            "bad game error shape",
            status == 400
            and isinstance(body, dict)
            and isinstance(detail, str)
            and "valid games" in detail.lower(),
            f"{status} detail={detail!r}",
            status,
            ms,
        )

        status, body, ms = timed(
            client,
            "POST",
            "/v1/similar",
            json={"game": "magic", "query": "Lightning Bolt", "top_k": "five"},
        )
        record(
            "validation error is readable",
            status == 422
            and isinstance(body, dict)
            and isinstance((body or {}).get("message"), str),
            f"{status} message={(body or {}).get('message')!r}",
            status,
            ms,
        )

    anomalies = [check for check in checks if not check["ok"]]
    payload = {
        "checks": checks,
        "anomalies": anomalies,
        "passed": len(checks) - len(anomalies),
        "total": len(checks),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    for check in checks:
        mark = "ok  " if check["ok"] else "FAIL"
        print(f"{mark} {check['check']}: {check['detail']} [{check['ms']}ms]")
    print(f"\n{payload['passed']}/{payload['total']} passed")
    return 0 if not anomalies else 1


if __name__ == "__main__":
    raise SystemExit(main())
