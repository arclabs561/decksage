#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""
Benchmark local LLM inference servers for annotation throughput.

Tests: single request latency, concurrent throughput, JSON compliance.
Reports: TTFT, tok/s, total throughput, error rate.

Usage:
    uv run scripts/annotation/bench_local_llm.py                    # test all detected servers
    uv run scripts/annotation/bench_local_llm.py --url http://localhost:8085/v1  # specific server
    uv run scripts/annotation/bench_local_llm.py --concurrency 8    # test at higher concurrency
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import requests


ANNOTATION_PROMPT = {
    "messages": [
        {
            "role": "system",
            "content": "You are a card game expert. Respond with JSON only.",
        },
        {
            "role": "user",
            "content": (
                "Rate these MAGIC cards (0.0-1.0):\n\n"
                "A: Type: Instant\nMana cost: {R}\n"
                "Text: Lightning Bolt deals 3 damage to any target.\n\n"
                "B: Type: Sorcery\nMana cost: {R}\n"
                "Text: Chain Lightning deals 3 damage to any target. "
                "Then that player may pay {R}{R}. If the player does, "
                "copy this spell.\n\n"
                "Anchors: 1.0=reprint, 0.8=same role, 0.6=similar function, "
                "0.4=same archetype, 0.2=tangential, 0.0=unrelated.\n"
                'Respond with JSON: {"similarity_score": 0.0, '
                '"functional_score": 0.0, "synergy_score": 0.0, '
                '"meta_relevance": 0.0}'
            ),
        },
    ],
    "temperature": 0.3,
    "max_tokens": 300,
}


# Card pairs for concurrent testing (diverse enough to avoid trivial caching)
CARD_PAIRS = [
    (
        "Lightning Bolt",
        "Chain Lightning",
        "Instant, {R}, 3 damage to any target",
        "Sorcery, {R}, 3 damage, copyable",
    ),
    (
        "Counterspell",
        "Mana Drain",
        "Instant, {U}{U}, counter target spell",
        "Instant, {U}{U}, counter + mana",
    ),
    (
        "Swords to Plowshares",
        "Path to Exile",
        "Instant, {W}, exile creature, life",
        "Instant, {W}, exile creature, land",
    ),
    (
        "Dark Ritual",
        "Cabal Ritual",
        "Instant, {B}, add BBB",
        "Instant, {1}{B}, add BBB if threshold",
    ),
    ("Brainstorm", "Ponder", "Instant, {U}, draw 3 put 2 back", "Sorcery, {U}, look at top 3"),
    (
        "Wrath of God",
        "Damnation",
        "Sorcery, {2}{W}{W}, destroy all",
        "Sorcery, {2}{B}{B}, destroy all",
    ),
    ("Sol Ring", "Mana Crypt", "Artifact, {1}, tap add 2", "Artifact, {0}, tap add 2, flip damage"),
    (
        "Thoughtseize",
        "Inquisition of Kozilek",
        "Sorcery, {B}, discard any nonland",
        "Sorcery, {B}, discard CMC<=3",
    ),
]


def detect_servers() -> list[dict]:
    """Auto-detect running local LLM servers."""
    candidates = [
        {"name": "mlx-lm", "url": "http://localhost:8085/v1", "port": 8085},
        {"name": "DMR/llama.cpp", "url": "http://localhost:12434/v1", "port": 12434},
        {"name": "ollama", "url": "http://localhost:11434/v1", "port": 11434},
        {"name": "vllm/sglang", "url": "http://localhost:8000/v1", "port": 8000},
    ]
    found = []
    for c in candidates:
        try:
            r = requests.get(f"{c['url']}/models", timeout=2)
            if r.status_code == 200:
                data = r.json()
                models = data.get("data", []) if isinstance(data, dict) else []
                model_id = models[0]["id"] if models else "unknown"
                c["model"] = model_id
                found.append(c)
        except Exception:
            pass
    return found


def single_request(url: str, model: str) -> dict:
    """Single request with detailed timing."""
    session = requests.Session()
    session.trust_env = False

    payload = {**ANNOTATION_PROMPT, "model": model, "stream": True}

    t0 = time.perf_counter()
    resp = session.post(
        f"{url}/chat/completions",
        json=payload,
        stream=True,
        timeout=120,
    )

    ttft = None
    chunks = []
    token_count = 0

    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8", errors="replace")
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content and ttft is None:
                    ttft = time.perf_counter() - t0
                if content:
                    chunks.append(content)
                    token_count += 1
            except json.JSONDecodeError:
                pass

    total_time = time.perf_counter() - t0
    full_content = "".join(chunks)

    # Try non-streaming fallback if streaming didn't work
    if not chunks:
        t0 = time.perf_counter()
        payload["stream"] = False
        resp = session.post(f"{url}/chat/completions", json=payload, timeout=120)
        total_time = time.perf_counter() - t0
        data = resp.json()
        if "choices" not in data:
            return {
                "ttft_ms": 0,
                "total_ms": total_time * 1000,
                "tokens": 0,
                "tok_per_sec": 0,
                "json_valid": False,
                "scores": None,
                "raw": str(data)[:200],
                "error": data.get("error", str(data)[:100]),
            }
        full_content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        token_count = usage.get("completion_tokens", len(full_content.split()))
        # Estimate TTFT from timings if available
        timings = data.get("timings", {})
        prompt_ms = timings.get("prompt_ms", 0)
        ttft = prompt_ms / 1000.0 if prompt_ms else total_time * 0.3

    # Validate JSON output
    json_valid = False
    parsed = None
    try:
        clean = full_content.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1].lstrip("json\n")
        parsed = json.loads(clean)
        required = {"similarity_score", "functional_score", "synergy_score", "meta_relevance"}
        json_valid = required.issubset(parsed.keys())
    except (json.JSONDecodeError, IndexError):
        pass

    gen_time = total_time - (ttft or 0)
    tok_per_sec = token_count / gen_time if gen_time > 0 else 0

    return {
        "ttft_ms": (ttft or 0) * 1000,
        "total_ms": total_time * 1000,
        "tokens": token_count,
        "tok_per_sec": tok_per_sec,
        "json_valid": json_valid,
        "scores": parsed if json_valid else None,
        "raw": full_content[:200],
    }


async def concurrent_test(url: str, model: str, concurrency: int = 4, n_requests: int = 8) -> dict:
    """Test concurrent throughput."""
    session = requests.Session()
    session.trust_env = False

    results = []
    sem = asyncio.Semaphore(concurrency)

    async def one_request(pair_idx: int) -> dict:
        async with sem:
            card_a, card_b, desc_a, desc_b = CARD_PAIRS[pair_idx % len(CARD_PAIRS)]
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a card game expert. Respond with JSON only.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Rate these MAGIC cards (0.0-1.0):\n\n"
                            f"A: {card_a} -- {desc_a}\n\n"
                            f"B: {card_b} -- {desc_b}\n\n"
                            'Respond with JSON: {"similarity_score": 0.0, '
                            '"functional_score": 0.0, "synergy_score": 0.0, '
                            '"meta_relevance": 0.0}'
                        ),
                    },
                ],
                "temperature": 0.3,
                "max_tokens": 300,
            }

            t0 = time.perf_counter()
            try:
                resp = await asyncio.to_thread(
                    session.post,
                    f"{url}/chat/completions",
                    json=payload,
                    timeout=120,
                )
                elapsed = time.perf_counter() - t0
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                tokens = usage.get("completion_tokens", len(content.split()))

                # Validate JSON
                valid = False
                try:
                    clean = content.strip()
                    if clean.startswith("```"):
                        clean = clean.split("```")[1].lstrip("json\n")
                    parsed = json.loads(clean)
                    valid = "similarity_score" in parsed
                except (json.JSONDecodeError, IndexError):
                    pass

                return {"ok": True, "ms": elapsed * 1000, "tokens": tokens, "json_valid": valid}
            except Exception as e:
                elapsed = time.perf_counter() - t0
                return {
                    "ok": False,
                    "ms": elapsed * 1000,
                    "tokens": 0,
                    "json_valid": False,
                    "error": str(e),
                }

    t_start = time.perf_counter()
    tasks = [one_request(i) for i in range(n_requests)]
    results = await asyncio.gather(*tasks)
    wall_time = time.perf_counter() - t_start

    ok_results = [r for r in results if r["ok"]]
    total_tokens = sum(r["tokens"] for r in ok_results)

    return {
        "concurrency": concurrency,
        "n_requests": n_requests,
        "successes": len(ok_results),
        "failures": len(results) - len(ok_results),
        "json_valid": sum(1 for r in ok_results if r["json_valid"]),
        "wall_time_ms": wall_time * 1000,
        "total_tokens": total_tokens,
        "aggregate_tok_per_sec": total_tokens / wall_time if wall_time > 0 else 0,
        "mean_latency_ms": statistics.mean(r["ms"] for r in ok_results) if ok_results else 0,
        "p50_latency_ms": statistics.median(r["ms"] for r in ok_results) if ok_results else 0,
        "p99_latency_ms": sorted(r["ms"] for r in ok_results)[int(len(ok_results) * 0.99)]
        if ok_results
        else 0,
        "requests_per_sec": len(ok_results) / wall_time if wall_time > 0 else 0,
    }


def format_report(name: str, url: str, model: str, single: dict, concurrent: dict) -> str:
    lines = [
        f"\n{'=' * 60}",
        f"  {name}",
        f"  URL: {url}  Model: {model}",
        f"{'=' * 60}",
        "",
        "  Single request:",
        f"    TTFT:       {single['ttft_ms']:>8.1f} ms",
        f"    Total:      {single['total_ms']:>8.1f} ms",
        f"    Tokens:     {single['tokens']:>8d}",
        f"    Tok/s:      {single['tok_per_sec']:>8.1f}",
        f"    JSON valid: {'PASS' if single['json_valid'] else 'FAIL'}",
        f"    Scores:     {single['scores']}",
        "",
        f"  Concurrent ({concurrent['concurrency']} parallel, {concurrent['n_requests']} requests):",
        f"    Wall time:  {concurrent['wall_time_ms']:>8.1f} ms",
        f"    Successes:  {concurrent['successes']}/{concurrent['n_requests']}",
        f"    JSON valid: {concurrent['json_valid']}/{concurrent['successes']}",
        f"    Total tok:  {concurrent['total_tokens']:>8d}",
        f"    Agg tok/s:  {concurrent['aggregate_tok_per_sec']:>8.1f}  (total throughput)",
        f"    Req/s:      {concurrent['requests_per_sec']:>8.2f}",
        f"    Mean lat:   {concurrent['mean_latency_ms']:>8.1f} ms",
        f"    P50 lat:    {concurrent['p50_latency_ms']:>8.1f} ms",
        f"    P99 lat:    {concurrent['p99_latency_ms']:>8.1f} ms",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Benchmark local LLM servers")
    parser.add_argument("--url", help="Server URL (e.g., http://localhost:8085/v1)")
    parser.add_argument("--model", help="Model name override")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent requests")
    parser.add_argument(
        "--requests", type=int, default=8, help="Total requests for concurrent test"
    )
    args = parser.parse_args()

    if args.url:
        # Auto-detect model from server
        model = args.model
        if not model:
            try:
                r = requests.get(f"{args.url}/models", timeout=5)
                models = r.json().get("data", [])
                model = models[0]["id"] if models else "default"
            except Exception:
                model = "default"
        servers = [{"name": "custom", "url": args.url, "model": model}]
    else:
        print("Detecting local LLM servers...")
        servers = detect_servers()
        if not servers:
            print("No local LLM servers detected. Start one of:")
            print(
                "  ./scripts/start_mlx_server.sh              # mlx-lm (fastest on Apple Silicon)"
            )
            print("  docker model run ai/qwen2.5:7B-Q4_K_M -d   # Docker Model Runner")
            print("  ollama serve                                # Ollama")
            return 1

    for srv in servers:
        print(f"\nDetected: {srv['name']} at {srv['url']} (model: {srv['model']})")

    print(f"\nRunning benchmarks (concurrency={args.concurrency}, requests={args.requests})...")

    for srv in servers:
        name = srv["name"]
        url = srv["url"]
        model = args.model or srv["model"]

        # Single request test
        print(f"\n  [{name}] Single request...", end="", flush=True)
        single = single_request(url, model)
        print(f" {single['tok_per_sec']:.1f} tok/s, TTFT {single['ttft_ms']:.0f}ms")

        # Concurrent test
        print(f"  [{name}] Concurrent ({args.concurrency}x)...", end="", flush=True)
        concurrent = asyncio.run(
            concurrent_test(url, model, concurrency=args.concurrency, n_requests=args.requests)
        )
        print(f" {concurrent['aggregate_tok_per_sec']:.1f} agg tok/s")

        # Report
        print(format_report(name, url, model, single, concurrent))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
