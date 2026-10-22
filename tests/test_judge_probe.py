"""Offline tests for `scripts/evaluation/judge_probe.py` (Stage 0 judge probes).

Covers the deterministic dry-run scorer, order-swap asymmetry detection on a
synthetic biased scorer, the resolution verdict thresholds from
docs/JUDGE-CALIBRATION.md, and the JSON report shape. No test makes a network
call or needs an API key.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "evaluation" / "judge_probe.py"

VERDICTS = {
    "resolution": {"usable", "compressed", "deflated", "concentrated", "absent"},
    "order_swap": {"invariant", "position_sensitive", "absent"},
    "rubric": {"keep_a", "keep_b", "flat", "rank_unstable", "insufficient", "absent"},
}


@pytest.fixture(scope="module")
def probe():
    """Load the probe script as a module (it lives outside the package).

    The module is registered in ``sys.modules`` first: ``@dataclass`` resolves
    annotations through ``cls.__module__`` and fails on an unregistered module.
    """
    spec = importlib.util.spec_from_file_location("judge_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def anchors(tmp_path, probe):
    """Six anchor pairs, two of them carrying a human score."""
    rows = [
        {
            "query": "Q1",
            "candidate": "C1",
            "query_text": "Draw two cards.",
            "candidate_text": "Draw one card.",
            "human_score": 0.8,
        },
        {
            "query": "Q2",
            "candidate": "C2",
            "query_text": "Counter target spell.",
            "candidate_text": "Destroy target land.",
        },
        {
            "query": "Q3",
            "candidate": "C3",
            "query_text": "Gain 3 life.",
            "candidate_text": "Gain 2 life.",
            "human_score": 0.6,
        },
        {
            "query": "Q4",
            "candidate": "C4",
            "query_text": "Exile a creature.",
            "candidate_text": "Exile an artifact.",
        },
        {"query": "Q5", "candidate": "C5", "query_text": "Scry 2.", "candidate_text": "Surveil 2."},
        {
            "query": "Q6",
            "candidate": "C6",
            "query_text": "Tap a land.",
            "candidate_text": "Untap a land.",
        },
    ]
    path = tmp_path / "anchors.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def score_all(probe, scorer, pairs, variant="a", swap=False):
    module_pairs = probe.parse_pairs(
        [
            {
                "query": p.query,
                "candidate": p.candidate,
                "query_text": p.query_text,
                "candidate_text": p.candidate_text,
            }
            for p in pairs
        ]
    )
    return probe._score(scorer, module_pairs, variant, swap=swap)


def loaded(probe, path):
    return probe.load_pairs(path)


class TestDryRunDeterminism:
    def test_same_seed_same_scores(self, probe, anchors):
        pairs = loaded(probe, anchors)
        first = probe.make_fake_scorer(seed=11)
        second = probe.make_fake_scorer(seed=11)
        base = score_all(probe, first, pairs)
        assert base == score_all(probe, second, pairs)
        assert base == score_all(probe, first, pairs)
        variant_b = score_all(probe, first, pairs, variant="b")
        assert variant_b == score_all(probe, second, pairs, variant="b")
        assert variant_b != base  # the rubric variant is a different wording
        assert all(0.0 <= value <= 1.0 for value in base + variant_b)

    def test_seed_changes_scores(self, probe, anchors):
        pairs = loaded(probe, anchors)
        assert score_all(probe, probe.make_fake_scorer(seed=1), pairs) != score_all(
            probe, probe.make_fake_scorer(seed=2), pairs
        )

    def test_report_is_reproducible_except_timestamp(self, probe, anchors):
        pairs = loaded(probe, anchors)

        def run():
            report = probe.run_probe(
                pairs, probe.make_fake_scorer(seed=3), dry_run=True, seed=3, model=None
            )
            report.pop("generated_at")
            return report

        assert run() == run()

    def test_default_fake_is_symmetric(self, probe, anchors):
        pairs = loaded(probe, anchors)
        scorer = probe.make_fake_scorer(seed=0)
        forward = score_all(probe, scorer, pairs)
        swapped = score_all(probe, scorer, pairs, swap=True)
        stats = probe.order_swap_stats(forward, swapped)
        assert stats["asymmetry_rate"] == 0.0
        assert stats["verdict"] == "invariant"


class TestOrderSwapAsymmetry:
    def test_detects_position_sensitive_scorer(self, probe):
        """A scorer that reads the query slot as "important" must be flagged."""
        pairs = probe.parse_pairs(
            [
                {
                    "query": f"Q{i}",
                    "candidate": f"C{i}",
                    "query_text": f"QUERY-TEXT-{i}",
                    "candidate_text": f"CANDIDATE-TEXT-{i}",
                }
                for i in range(4)
            ]
        )

        def positional(query_text, candidate_text, variant):
            return 0.9 if query_text.startswith("QUERY") else 0.1

        forward = probe._score(positional, pairs, "a")
        swapped = probe._score(positional, pairs, "a", swap=True)
        stats = probe.order_swap_stats(forward, swapped)
        assert stats["n"] == len(pairs)
        assert stats["asymmetry_rate"] == 1.0
        assert stats["mean_signed_delta"] == pytest.approx(-0.8)
        assert stats["mean_abs_delta"] == pytest.approx(0.8)
        assert stats["verdict"] == "position_sensitive"

    def test_detects_biased_fake_scorer(self, probe, anchors):
        pairs = loaded(probe, anchors)
        scorer = probe.make_fake_scorer(seed=4, position_bias=0.15)
        stats = probe.order_swap_stats(
            score_all(probe, scorer, pairs), score_all(probe, scorer, pairs, swap=True)
        )
        assert stats["asymmetry_rate"] > 0.5
        assert stats["verdict"] == "position_sensitive"

    def test_deltas_below_tolerance_are_invariant(self, probe):
        forward = [0.50, 0.60, 0.70]
        swapped = [0.505, 0.598, 0.703]
        assert probe.order_swap_stats(forward, swapped)["verdict"] == "invariant"
        assert probe.order_swap_stats(forward, swapped, tolerance=0.0)["verdict"] == (
            "position_sensitive"
        )


class TestResolutionVerdicts:
    def test_spread_is_usable(self, probe):
        values = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
        stats = probe.resolution_stats(values)
        assert stats["sd"] > probe.SD_COMPRESSED
        assert stats["distinct"] == 10
        assert stats["verdict"] == "usable"

    def test_low_sd_is_compressed(self, probe):
        stats = probe.resolution_stats([0.50, 0.51, 0.52, 0.51, 0.50, 0.52])
        assert stats["sd"] < probe.SD_COMPRESSED
        assert stats["verdict"] == "compressed"

    def test_dominant_top_bin_is_compressed(self, probe):
        values = [0.95] * 17 + [0.10, 0.30, 0.50]
        stats = probe.resolution_stats(values)
        assert stats["sd"] > probe.SD_COMPRESSED  # sd alone would pass
        assert stats["top_bin_share"] == pytest.approx(0.85)
        assert stats["verdict"] == "compressed"

    def test_zero_heavy_is_deflated(self, probe):
        values = [0.0] * 15 + [0.5, 0.6, 0.7, 0.8, 0.9]
        stats = probe.resolution_stats(values)
        assert stats["zero_share"] > probe.ZERO_DEFLATED
        assert stats["top_bin_share"] <= probe.TOP_BIN_COMPRESSED
        assert stats["sd"] > probe.SD_COMPRESSED
        assert stats["verdict"] == "deflated"

    def test_one_bin_concentration_is_reported(self, probe):
        values = [0.0] * 14 + [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        stats = probe.resolution_stats(values)
        assert stats["zero_share"] == pytest.approx(0.7)  # not above the deflation line
        assert stats["verdict"] == "concentrated"

    @pytest.mark.parametrize(
        ("sd", "top_bin", "zero", "expected"),
        [
            (0.049, 0.4, 0.0, "compressed"),
            (0.05, 0.4, 0.0, "usable"),
            (0.30, 0.81, 0.0, "compressed"),
            (0.30, 0.80, 0.0, "concentrated"),
            (0.30, 0.61, 0.0, "concentrated"),
            (0.30, 0.30, 0.71, "deflated"),
            (0.30, 0.30, 0.70, "usable"),
        ],
    )
    def test_threshold_boundaries(self, probe, sd, top_bin, zero, expected):
        assert probe.resolution_verdict(sd, top_bin, zero) == expected


class TestRankCorrelation:
    def test_monotone_transform_is_one(self, probe):
        values = [0.1, 0.4, 0.35, 0.9, 0.7]
        assert probe.rank_correlation(values, [0.5 + (v - 0.5) * 0.8 for v in values]) == 1.0

    def test_ties_use_average_ranks(self, probe):
        assert probe.rank_correlation([0.1, 0.1, 0.2, 0.9], [0.2, 0.2, 0.3, 0.8]) == 1.0

    def test_reversed_ranking_is_negative_one(self, probe):
        assert probe.rank_correlation([0.1, 0.2, 0.3, 0.4], [0.9, 0.8, 0.7, 0.6]) == -1.0

    def test_undefined_without_variance(self, probe):
        assert probe.rank_correlation([0.5, 0.5, 0.5], [0.1, 0.2, 0.3]) is None
        assert probe.rank_correlation([0.1, 0.2], [0.3, 0.4]) is None


class TestJsonShape:
    @staticmethod
    def run_cli(probe, capsys, *args):
        code = probe.main(list(args))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    def test_json_report_shape(self, probe, anchors, capsys):
        code, out, err = self.run_cli(
            probe, capsys, "--pairs", str(anchors), "--dry-run", "--json", "--seed", "5"
        )
        assert code == 0, err
        report = json.loads(out)
        assert report["schema"] == "judge_probe.v1"
        assert report["scorer"] == "dry-run"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:+.-]+", report["generated_at"])

        inputs = report["inputs"]
        assert inputs["n_pairs"] == 6
        assert inputs["n_labelled"] == 2
        assert inputs["dry_run"] is True
        assert inputs["seed"] == 5
        assert inputs["limit"] is None
        assert sorted(inputs["modes"]) == ["order-swap", "resolution", "rubric"]

        modes = report["modes"]
        assert set(modes) == {"resolution", "order_swap", "rubric"}
        assert set(modes["resolution"]) >= {
            "n",
            "mean",
            "sd",
            "distinct",
            "effective_distinct",
            "tie_rate",
            "zero_share",
            "top_bin_share",
            "histogram",
            "verdict",
            "calls",
        }
        assert set(modes["order_swap"]) >= {
            "n",
            "asymmetry_rate",
            "mean_abs_delta",
            "max_abs_delta",
            "mean_signed_delta",
            "verdict",
            "calls",
        }
        assert set(modes["rubric"]) >= {
            "n",
            "variant_a",
            "variant_b",
            "sd_delta",
            "rank_corr",
            "n_labelled",
            "human_rank_corr",
            "anchor_guard",
            "verdict",
            "calls",
        }
        for name, allowed in VERDICTS.items():
            assert modes[name]["verdict"] in allowed
        assert len(modes["resolution"]["histogram"]) == 10
        assert sum(modes["resolution"]["histogram"]) == 6
        # Forward scores are shared by resolution and rubric: 6 + 6 + 6 calls.
        assert report["calls_total"] == 18
        assert report["calls_total"] == sum(mode["calls"] for mode in modes.values())

    def test_table_output(self, probe, anchors, capsys):
        code, out, err = self.run_cli(probe, capsys, "--pairs", str(anchors), "--dry-run")
        assert code == 0, err
        assert "resolution" in out
        assert "order-swap" in out
        assert "rubric" in out
        assert "verdict=invariant" in out
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)  # table mode is not JSON

    def test_limit_caps_pairs(self, probe, anchors, capsys):
        code, out, err = self.run_cli(
            probe, capsys, "--pairs", str(anchors), "--dry-run", "--json", "--limit", "3"
        )
        assert code == 0, err
        report = json.loads(out)
        assert report["inputs"]["n_pairs"] == 3
        assert report["inputs"]["limit"] == 3
        assert report["modes"]["resolution"]["n"] == 3

    def test_single_mode_only_reports_that_mode(self, probe, anchors, capsys):
        code, out, err = self.run_cli(
            probe, capsys, "--pairs", str(anchors), "--dry-run", "--json", "--mode", "order-swap"
        )
        assert code == 0, err
        report = json.loads(out)
        assert set(report["modes"]) == {"order_swap"}
        assert report["modes"]["order_swap"]["n"] == 6
        assert report["calls_total"] == 12  # forward + swapped

    def test_missing_key_fails_before_any_call(self, probe, anchors, capsys, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        code, out, err = self.run_cli(probe, capsys, "--pairs", str(anchors), "--json")
        assert code == 2
        assert out == ""
        assert "OPENROUTER_API_KEY" in err
        assert "--dry-run" in err

    def test_bad_anchor_line_reports_the_line(self, probe, tmp_path, capsys):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"query": "Q", "candidate": "C"}\n{"query": "", "candidate": "C"}\n')
        code, out, err = self.run_cli(probe, capsys, "--pairs", str(path), "--dry-run")
        assert code == 2
        assert out == ""
        assert "line 2" in err

    def test_missing_file_is_a_clean_error(self, probe, tmp_path, capsys):
        code, _out, err = self.run_cli(
            probe, capsys, "--pairs", str(tmp_path / "nope.jsonl"), "--dry-run"
        )
        assert code == 2
        assert "anchor file not found" in err


class TestScoreParsing:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [("0.7", 0.7), ("Score: 0.42", 0.42), ("1", 1.0), ("  0.05\n", 0.05)],
    )
    def test_parse_score(self, probe, content, expected):
        body = {"choices": [{"message": {"content": content}}]}
        assert probe.parse_score(body) == expected

    def test_rejects_non_numeric_reply(self, probe):
        body = {"choices": [{"message": {"content": "similar, I think"}}]}
        with pytest.raises(probe.ProbeError, match="no number"):
            probe.parse_score(body)

    def test_rejects_out_of_range(self, probe):
        body = {"choices": [{"message": {"content": "7"}}]}
        with pytest.raises(probe.ProbeError, match="outside"):
            probe.parse_score(body)
