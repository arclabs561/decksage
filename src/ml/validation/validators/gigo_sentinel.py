#!/usr/bin/env python3
"""
GIGO Sentinel: surfaces likely data extraction/quality issues.

Detects:
- Structural anomalies (already covered elsewhere but summarized here)
- Statistical outliers in co-occurrence and price data
- Optional LLM audit on sampled records (if OPENROUTER_API_KEY is set)

Outputs a JSON-serializable dict of findings with severity/confidence.
"""

from __future__ import annotations

import os
import statistics as stats
from collections import defaultdict


try:
    from pydantic import BaseModel, Field

    from ...utils.pydantic_ai_helpers import make_agent

    HAS_PYDANTIC_AI = True
except Exception:
    HAS_PYDANTIC_AI = False
    BaseModel = object  # type: ignore[assignment]
    Field = object  # type: ignore[assignment]

    def make_agent(*args, **kwargs):  # type: ignore
        raise RuntimeError("pydantic-ai helpers unavailable")


def summarize_structural(structural_issues: list[tuple]) -> list[dict]:
    findings: list[dict] = []
    for line_num, deck_id, issues in structural_issues[:50]:
        findings.append(
            {
                "type": "structural_issue",
                "severity": "high",
                "deck_id": deck_id,
                "line": line_num,
                "issues": issues,
                "confidence": 0.95,
            }
        )
    return findings


def detect_cooccurrence_outliers(pairs_df) -> list[dict]:
    findings: list[dict] = []
    if pairs_df is None or len(pairs_df) == 0:
        return findings

    cnt = pairs_df["COUNT_MULTISET"].astype(float)
    n = len(cnt)

    # Robust thresholding for small samples; classic z for large n
    if n < 1000:
        median = stats.median(cnt)
        mad = stats.median([abs(x - median) for x in cnt]) or 1.0
        high = median + 9 * mad  # tolerant but will flag egregious spikes
    else:
        mean = float(cnt.mean())
        std = float(cnt.std() or 1.0)
        high = mean + 6 * std

    for _, row in pairs_df.iterrows():
        c = float(row["COUNT_MULTISET"])
        if c > high:
            findings.append(
                {
                    "type": "cooccurrence_outlier_high",
                    "severity": "medium",
                    "pair": [row["NAME_1"], row["NAME_2"]],
                    "count": c,
                    "threshold": high,
                    "confidence": 0.8,
                    "suggested_fix": "Verify scraper pagination and deduplication.",
                }
            )
        # We only flag high outliers for now to avoid noise
    return findings


def detect_price_outliers(price_records: list[dict]) -> list[dict]:
    findings: list[dict] = []
    if not price_records:
        return findings

    prices = [float(r.get("usd", 0) or 0) for r in price_records]
    if not prices:
        return findings

    median = stats.median(prices)
    mad = stats.median([abs(p - median) for p in prices]) or 1.0
    high = median + 15 * mad

    for r in price_records:
        p = float(r.get("usd", 0) or 0)
        if p > high and p > 1000.0:
            findings.append(
                {
                    "type": "price_outlier_high",
                    "severity": "low",
                    "card": r.get("name"),
                    "price_usd": p,
                    "threshold": high,
                    "confidence": 0.7,
                    "suggested_fix": "Check currency parsing and decimals.",
                }
            )
    return findings


def llm_audit_samples(records: list[dict], task: str = "deck_coherence") -> list[dict]:
    findings: list[dict] = []
    if not os.getenv("OPENROUTER_API_KEY"):
        return findings

    if not HAS_PYDANTIC_AI:
        return findings

    class AuditFinding(BaseModel):
        issue: str = Field(description="One-line issue summary")
        severity: str = Field(description="low|medium|high")
        confidence: float = Field(ge=0.0, le=1.0)
        suggested_fix: str

    class AuditResult(BaseModel):
        findings: list[AuditFinding]

    system = (
        "You are a strict data auditor. Given a parsed record, flag likely extraction errors.\n"
        "Focus on mismatches (wrong archetype, broken encoding, duplicated entries). Keep it concise."
    )
    agent = make_agent("anthropic/claude-4.5-sonnet", AuditResult, system)

    for rec in records[:10]:
        prompt = f"Record to audit (JSON):\n{rec}"
        try:
            res = agent.run_sync(prompt)
            findings.extend(
                [
                    {
                        "type": "llm_audit",
                        "severity": f.severity,
                        "issue": f.issue,
                        "suggested_fix": f.suggested_fix,
                        "confidence": f.confidence,
                    }
                    for f in res.output.findings
                ]
            )
        except Exception:
            continue
    return findings


def run_sentinel(
    pairs_df=None,
    price_records: list[dict] | None = None,
    structural_issues=None,
    sample_records=None,
) -> dict:
    all_findings: list[dict] = []
    if structural_issues:
        all_findings.extend(summarize_structural(structural_issues))
    if pairs_df is not None:
        all_findings.extend(detect_cooccurrence_outliers(pairs_df))
    if price_records:
        all_findings.extend(detect_price_outliers(price_records))
    if sample_records:
        all_findings.extend(llm_audit_samples(sample_records))

    # Group by type for summary
    summary = defaultdict(int)
    for f in all_findings:
        summary[f.get("type", "unknown")] += 1

    return {"summary": dict(summary), "findings": all_findings}


__all__ = ["detect_cooccurrence_outliers", "detect_price_outliers", "run_sentinel"]
