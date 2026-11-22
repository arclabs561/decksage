from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from ml.similarity import visual_embeddings as visual


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_streamed_image_and_cache(tmp_path, monkeypatch, fmt):
    embedder = SimpleNamespace(image_cache_dir=tmp_path)
    data = BytesIO()
    Image.new("RGB", (3, 2)).save(data, format=fmt)
    response = MagicMock()
    response.iter_content.return_value = [data.getvalue()]
    get = MagicMock()
    get.return_value.__enter__.return_value = response
    monkeypatch.setattr(visual.requests, "get", get)
    for _ in range(2):
        image = visual.CardVisualEmbedder._download_image(embedder, "https://example.org/card")
        assert (image.mode, image.size) == ("RGB", (3, 2))
    get.assert_called_once()


def test_input_limits(tmp_path, monkeypatch):
    embedder = SimpleNamespace(image_cache_dir=tmp_path)
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b"abc", b"def"]
    monkeypatch.setattr(visual.requests, "get", lambda *a, **kw: response)
    monkeypatch.setattr(visual, "_MAX_CARD_BYTES", 4)
    assert visual.CardVisualEmbedder._download_image(embedder, "https://example.org/card") is None
    response.__exit__.assert_called_once()
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(visual, "_MAX_CARD_PIXELS", 5)
    for fmt in ("PNG", "BMP"):
        data = BytesIO()
        Image.new("RGB", (3, 2)).save(data, format=fmt)
        with pytest.raises((ValueError, OSError)):
            visual._decode_card_image(data)
