from unittest.mock import Mock, call

from ml.api import chat


def test_agent_cache_is_scoped_to_game(monkeypatch):
    factory = Mock(side_effect=lambda game: object())
    monkeypatch.setattr(chat, "_build_agent", factory)
    monkeypatch.setattr(chat, "_agents", {})

    magic = chat._get_agent("magic")
    assert chat._get_agent("magic") is magic
    assert chat._get_agent("yugioh") is not magic
    assert factory.call_args_list == [call("magic"), call("yugioh")]
