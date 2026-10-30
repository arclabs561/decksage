"""Judges receive complete card context and game-appropriate guidance."""

import asyncio
import importlib.util
from pathlib import Path


def load_diverse():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/annotate_diverse_pairs.py"
    spec = importlib.util.spec_from_file_location("diverse_context", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_context_contains_full_rules_and_stats():
    module = load_diverse()
    text = "A" * 350 + " decisive restriction"
    context = module._card_context(
        "Card",
        {"Card": {"type_line": "Creature", "oracle_text": text, "power": "2", "toughness": "3"}},
    )
    assert text in context
    assert "Creature" in context
    assert "2/3" in context


def test_shared_context_prefers_enriched_metadata_and_skips_missing_rules(tmp_path):
    from ml.annotation.card_context import load_card_context

    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "card_attributes_magic_enriched.csv").write_text(
        "name,type,oracle_text,power,toughness\nA,Creature,Draw a card.,2,3\nB,Creature,,1,1\n"
    )
    (processed / "card_attributes_enriched.csv").write_text(
        "name,type,oracle_text\nOld,Instant,Old rules.\n"
    )
    context = load_card_context(tmp_path, "magic")
    assert set(context) == {"A"}
    assert "Name: A" in context["A"]
    assert "Power/toughness: 2/3" in context["A"]
    assert "Text: Draw a card." in context["A"]


def test_missing_rules_context_does_not_call_judge():
    module = load_diverse()

    class Agent:
        async def run(self, prompt):
            raise AssertionError("judge must not be called without card rules")

    async def run():
        return await module.annotate_pair(
            Agent(),
            "A",
            "B",
            {},
            "magic",
            {"A": {"oracle_text": "Draw a card."}},
            asyncio.Semaphore(1),
        )

    assert asyncio.run(run()) is None


def test_non_magic_prompt_does_not_use_magic_examples():
    module = load_diverse()
    prompt = module._build_annotation_prompt("a", "b", "pokemon")
    assert "Lightning Bolt" not in prompt


def test_cascade_uses_game_specific_anchors():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/multi_model_annotate.py"
    spec = importlib.util.spec_from_file_location("multi_model_annotate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    pokemon = module.build_annotation_prompt("A rules", "B rules", "pokemon")
    magic = module.build_annotation_prompt("A rules", "B rules", "magic")
    assert "Lightning Bolt" not in pokemon
    assert "Lightning Bolt" in magic


def test_convergence_skips_pairs_with_missing_rules():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/annotation_convergence.py"
    spec = importlib.util.spec_from_file_location("convergence_context", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    result = asyncio.run(
        module.annotate_pairs([("A", "B", "test")], "magic", {"A": "Text: Draw a card."})
    )
    assert result == []


def test_cascade_failure_does_not_create_zero_judgment(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/multi_model_annotate.py"
    spec = importlib.util.spec_from_file_location("cascade_failure", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    async def failed(*args):
        return {"scores": {}, "confidence": 0, "n_samples": 0, "needs_escalation": True}

    monkeypatch.setattr(module, "tier1_annotate", failed)
    result = asyncio.run(module.annotate_pair("A", "B", "Text: a", "Text: b", "magic"))
    assert result is None


def test_cascade_rejects_partial_model_output(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/multi_model_annotate.py"
    spec = importlib.util.spec_from_file_location("cascade_partial", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"similarity_score": 0.8}'}}]}

    class Session:
        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(module.requests, "Session", Session)
    monkeypatch.setenv("TEST_JUDGE_KEY", "test")
    model = {
        "api_key_env": "TEST_JUDGE_KEY",
        "api_url": "https://example.test",
        "model": "fake",
        "name": "fake",
    }
    result = asyncio.run(module.call_model(model, "A", "B", "Text: a", "Text: b", "magic"))
    assert result is None


def test_scale_prompt_hides_embedding_score_and_preserves_rules():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/scale_annotations.py"
    spec = importlib.util.spec_from_file_location("scale_context", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    captured = []

    class Agent:
        async def run(self, prompt):
            captured.append(prompt)
            raise RuntimeError("test")

    long_text = "Rules " * 60 + "important ending"
    cards = {"A": {"oracle_text": long_text}, "B": {"oracle_text": "Other rules"}}
    asyncio.run(
        module.annotate_pair_with_mode(Agent(), "A", "B", 0.876, "pokemon", card_data=cards)
    )
    assert "0.876" not in captured[0]
    assert "Lightning Bolt" not in captured[0]
    assert "important ending" in captured[0]
