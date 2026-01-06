#!/usr/bin/env python3
"""
Card visual embeddings using vision-language models (CLIP/SigLIP).

Provides visual similarity based on card images.
This is a primary signal for card similarity (expected 20% weight in fusion).
"""

from __future__ import annotations

import hashlib
import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("decksage.visual_embeddings")

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None
    logger.warning(
        "sentence-transformers not installed. Install with: uv add sentence-transformers"
    )

# Patch SigLIP config compatibility before any model loading
def _patch_siglip_config():
    """
    Patch SiglipConfig to work with sentence-transformers.
    
    sentence-transformers expects config.hidden_size, but SigLIP stores it in
    config.vision_config.hidden_size. This patch adds a hidden_size property
    that reads from vision_config.
    """
    try:
        from transformers import SiglipConfig
        
        # Only patch if not already patched and if hidden_size doesn't exist
        if not hasattr(SiglipConfig, '_siglip_patched'):
            if not hasattr(SiglipConfig, 'hidden_size') or not isinstance(
                getattr(SiglipConfig, 'hidden_size', None), property
            ):
                def _get_hidden_size(self):
                    """Get hidden_size from vision_config for sentence-transformers compatibility."""
                    if hasattr(self, 'vision_config') and hasattr(self.vision_config, 'hidden_size'):
                        return self.vision_config.hidden_size
                    raise AttributeError(
                        f"'{self.__class__.__name__}' object has no attribute 'hidden_size' "
                        f"and vision_config.hidden_size is not available"
                    )
                
                SiglipConfig.hidden_size = property(_get_hidden_size)
                SiglipConfig._siglip_patched = True
                logger.debug("Patched SiglipConfig.hidden_size for sentence-transformers compatibility")
    except ImportError:
        pass  # transformers not available, skip patching


# Apply patch on module import
_patch_siglip_config()

try:
    from PIL import Image
except ImportError:
    Image = None
    logger.warning("PIL/Pillow not installed. Install with: uv add pillow")

try:
    import requests
except ImportError:
    requests = None
    logger.warning("requests not installed. Install with: uv add requests")


class CardVisualEmbedder:
    """
    Embed cards using their visual content (images).

    Uses sentence-transformers with vision models (CLIP/SigLIP) for efficient visual embeddings.
    Caches embeddings and images to disk for performance.
    """

    def __init__(
        self,
        model_name: str = "google/siglip-base-patch16-224",  # SigLIP (better than CLIP, patched for compatibility)
        cache_dir: Path | str | None = None,
        image_cache_dir: Path | str | None = None,
        image_size: int = 224,
    ):
        """
        Initialize visual embedder.

        Args:
            model_name: Vision model name (CLIP or SigLIP)
            cache_dir: Directory to cache embeddings (default: .cache/visual_embeddings/)
            image_cache_dir: Directory to cache downloaded images (default: .cache/card_images/)
            image_size: Target image size for preprocessing (default: 224)
        """
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers required. Install with: uv add sentence-transformers"
            )

        if Image is None:
            raise ImportError("PIL/Pillow required. Install with: uv add pillow")

        if requests is None:
            raise ImportError("requests required. Install with: uv add requests")

        # Set attributes before model loading (needed for test image and cache setup)
        self.model_name = model_name
        self._memory_cache: dict[str, np.ndarray] = {}
        self.image_size = image_size
        
        # Setup cache directories (before model loading so cache_file is always set)
        if cache_dir is None:
            cache_dir = Path(".cache") / "visual_embeddings"
        else:
            cache_dir = Path(cache_dir)

        if image_cache_dir is None:
            image_cache_dir = Path(".cache") / "card_images"
        else:
            image_cache_dir = Path(image_cache_dir)

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Use model name for cache file (set before model loading)
        cache_model_name = self.model_name.replace('/', '_')
        self.cache_file = self.cache_dir / f"{cache_model_name}.pkl"

        self.image_cache_dir = image_cache_dir
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine if we should use transformers directly (for SigLIP) or sentence-transformers (for CLIP)
        use_transformers_direct = model_name.startswith("google/siglip")
        
        if use_transformers_direct:
            # SigLIP: Use transformers directly (sentence-transformers has compatibility issues)
            try:
                from transformers import AutoModel, AutoProcessor
                import torch
                
                self.processor = AutoProcessor.from_pretrained(model_name)
                self.vision_model = AutoModel.from_pretrained(model_name)
                self.vision_model.eval()
                self._use_transformers = True
                self._sentence_transformer = None
                self.model = None  # Not used for SigLIP
                
                logger.info(f"Loaded SigLIP model with transformers: {model_name}")
                
                # Verify model works and get embedding dimension
                test_img = Image.new("RGB", (self.image_size, self.image_size))
                inputs = self.processor(images=test_img, return_tensors="pt")
                with torch.no_grad():
                    outputs = self.vision_model.get_image_features(**inputs)
                test_emb = outputs[0].cpu().numpy()
                
                self._embedding_dim = len(test_emb)
                logger.info(f"Model embedding dimension: {self._embedding_dim}")
                
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load SigLIP model '{model_name}': {e}\n"
                    f"Install dependencies: uv add transformers pillow torch\n"
                    f"Fallback option: Use 'clip-ViT-B-16' with sentence-transformers"
                ) from e
        else:
            # CLIP: Use sentence-transformers (works out of the box)
            try:
                self.model = SentenceTransformer(model_name)
                self._use_transformers = False
                self._sentence_transformer = self.model
                self.processor = None
                self.vision_model = None
                
                logger.info(f"Loaded visual embedding model: {model_name}")
                
                # Verify model works by encoding a test image and get embedding dimension
                test_img = Image.new("RGB", (self.image_size, self.image_size))
                test_emb = self.model.encode(test_img, convert_to_numpy=True)
                self._embedding_dim = len(test_emb)
                logger.info(f"Model embedding dimension: {self._embedding_dim}")
                
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load visual embedding model '{model_name}': {e}\n"
                    f"Install dependencies: uv add sentence-transformers pillow\n"
                    f"Recommended models: 'google/siglip-base-patch16-224' (768D, best) "
                    f"or 'clip-ViT-B-16' (512D, fallback)"
                ) from e

        # Load existing cache
        self._load_cache()

    def _load_cache(self) -> None:
        """Load embeddings from disk cache."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "rb") as f:
                    self._memory_cache = pickle.load(f)
                logger.info(f"Loaded {len(self._memory_cache)} cached visual embeddings")
            except Exception as e:
                logger.warning(f"Failed to load visual embedding cache: {e}")
                self._memory_cache = {}

    def _save_cache(self) -> None:
        """Save embeddings to disk cache."""
        try:
            # During Python shutdown, builtins and modules may be unavailable
            import sys

            if sys.meta_path is None:
                return  # Python is shutting down, skip cache save

            with open(self.cache_file, "wb") as f:
                pickle.dump(self._memory_cache, f)
            logger.debug(f"Saved {len(self._memory_cache)} visual embeddings to cache")
        except (Exception, NameError, AttributeError) as e:
            # Silently fail during shutdown - logger may also be unavailable
            try:
                import sys

                if sys.meta_path is not None:  # Only log if not shutting down
                    logger.warning(f"Failed to save visual embedding cache: {e}")
            except Exception:
                pass  # Logger unavailable during shutdown

    def _get_image_url(self, card: dict[str, Any] | str) -> str | None:
        """
        Extract image URL from card dict.

        Supports multiple card data formats:
        - Scryfall (Magic): image_uris.png, image_url
        - Pokemon TCG: images.large, images.small
        - Yu-Gi-Oh: images[0].url, card_images[0].image_url
        - Riftcodex: media.image_url

        Args:
            card: Card dict or name string

        Returns:
            Image URL or None if not found
        """
        if isinstance(card, str):
            return None  # Can't extract URL from string

        # Try various image URL fields (order matters - most specific first)
        # Direct image URL fields
        if "image_url" in card and card["image_url"]:
            return card["image_url"]
        if "image" in card and card["image"]:
            return card["image"]
        
        # Scryfall format: image_uris.png
        if "image_uris" in card and isinstance(card["image_uris"], dict):
            return card["image_uris"].get("png") or card["image_uris"].get("large") or card["image_uris"].get("normal")
        
        # Pokemon TCG format: images.large
        if "images" in card:
            images = card["images"]
            if isinstance(images, dict):
                return images.get("large") or images.get("small") or images.get("png") or images.get("url")
            if isinstance(images, list) and len(images) > 0:
                if isinstance(images[0], dict):
                    return images[0].get("url") or images[0].get("URL") or images[0].get("image_url")
                if isinstance(images[0], str):
                    return images[0]
        
        # Yu-Gi-Oh format: card_images[0].image_url
        if "card_images" in card and isinstance(card["card_images"], list) and len(card["card_images"]) > 0:
            img = card["card_images"][0]
            if isinstance(img, dict):
                return img.get("image_url") or img.get("image_url_small") or img.get("url")
        
        # Riftcodex format: media.image_url
        if "media" in card and isinstance(card["media"], dict):
            return card["media"].get("image_url") or card["media"].get("url")
        
        # Handle card faces for multi-faced cards (e.g., Magic DFCs)
        if "card_faces" in card and isinstance(card["card_faces"], list) and len(card["card_faces"]) > 0:
            face = card["card_faces"][0]
            if "image_uris" in face and isinstance(face["image_uris"], dict):
                return face["image_uris"].get("png") or face["image_uris"].get("large")

        return None

    def _get_cache_key(self, card: dict[str, Any] | str | Image.Image) -> str:
        """
        Generate cache key for card/image.

        Args:
            card: Card dict, name string, or PIL Image

        Returns:
            Cache key string
        """
        if isinstance(card, Image.Image):
            # For PIL Image, use hash of image data
            import io

            img_bytes = io.BytesIO()
            card.save(img_bytes, format="PNG")
            img_hash = hashlib.sha256(img_bytes.getvalue()).hexdigest()
            return f"image_{img_hash}"

        if isinstance(card, str):
            return f"name_{card}"

        # For card dict, check if it has PIL Image directly
        if isinstance(card, dict) and "image" in card and isinstance(card["image"], Image.Image):
            # Use hash of PIL Image data
            import io
            img_bytes = io.BytesIO()
            card["image"].save(img_bytes, format="PNG")
            img_hash = hashlib.sha256(img_bytes.getvalue()).hexdigest()
            return f"image_{img_hash}"

        # For card dict, use image URL if available, otherwise card name
        image_url = self._get_image_url(card)
        if image_url:
            # Use hash of URL for cache key
            url_hash = hashlib.sha256(image_url.encode()).hexdigest()
            return f"url_{url_hash}"

        # Fallback to card name
        card_name = card.get("name", str(card))
        return f"name_{card_name}"

    def _download_image(self, url: str, max_retries: int = 3) -> Image.Image | None:
        """
        Download image from URL with caching.

        Args:
            url: Image URL
            max_retries: Maximum number of retry attempts

        Returns:
            PIL Image or None if download fails
        """
        # Check image cache first
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        cached_path = self.image_cache_dir / f"{url_hash}.png"

        if cached_path.exists():
            try:
                return Image.open(cached_path).convert("RGB")
            except Exception as e:
                logger.warning(f"Failed to load cached image {cached_path}: {e}")

        # Download image with retries and exponential backoff
        headers = {"User-Agent": "DeckSage/1.0 (https://decksage.com)"}
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=10, stream=True, headers=headers)
                response.raise_for_status()

                # Load image from bytes (more reliable than response.raw)
                from io import BytesIO
                img = Image.open(BytesIO(response.content)).convert("RGB")

                # Cache it
                try:
                    img.save(cached_path, "PNG")
                except Exception as e:
                    logger.debug(f"Failed to cache image: {e}")

                return img
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout downloading image from {url} (attempt {attempt + 1}/{max_retries})")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to download image from {url} (attempt {attempt + 1}/{max_retries}): {e}")
            except Exception as e:
                logger.error(f"Unexpected error downloading {url} (attempt {attempt + 1}/{max_retries}): {e}")
            
            # Exponential backoff
            if attempt < max_retries - 1:
                import time
                time.sleep(2 ** attempt)  # 1s, 2s, 4s...

        logger.warning(f"Failed to download image after {max_retries} attempts: {url}")
        return None

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for model input.

        Args:
            image: PIL Image

        Returns:
            Preprocessed PIL Image
        """
        # Resize to target size (maintain aspect ratio, then center crop)
        # Most vision models expect square images
        image.thumbnail((self.image_size, self.image_size), Image.Resampling.LANCZOS)

        # Create square image with center crop
        width, height = image.size
        if width != height:
            size = min(width, height)
            left = (width - size) // 2
            top = (height - size) // 2
            right = left + size
            bottom = top + size
            image = image.crop((left, top, right, bottom))

        # Resize to exact size
        image = image.resize((self.image_size, self.image_size), Image.Resampling.LANCZOS)

        return image

    def _card_to_image(self, card: dict[str, Any] | str | Image.Image) -> Image.Image | None:
        """
        Convert card to PIL Image.

        Args:
            card: Card dict, name string, or PIL Image

        Returns:
            PIL Image or None if conversion fails
        """
        # If already a PIL Image, return it
        if isinstance(card, Image.Image):
            return self._preprocess_image(card)

        # If string, can't get image
        if isinstance(card, str):
            logger.debug(f"Cannot get image from card name string: {card}")
            return None

        # Check if card dict has PIL Image directly (for testing/advanced usage)
        if isinstance(card, dict):
            # Check for PIL Image in 'image' field (not just URL)
            if "image" in card and isinstance(card["image"], Image.Image):
                return self._preprocess_image(card["image"])

        # Extract image URL from card dict
        image_url = self._get_image_url(card)
        if not image_url:
            logger.debug(f"No image URL found for card: {card.get('name', 'unknown')}")
            return None

        # Download image
        image = self._download_image(image_url)
        if image is None:
            return None

        return self._preprocess_image(image)

    def embed_card(self, card: dict[str, Any] | str | Image.Image) -> np.ndarray:
        """
        Embed a card using its visual content.

        Args:
            card: Card dict with image URL, card name string, or PIL Image

        Returns:
            Embedding vector (numpy array)
        """
        # Generate cache key
        cache_key = self._get_cache_key(card)

        # Check cache first
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        # Get image
        image = self._card_to_image(card)
        if image is None:
            # Return zero vector if image unavailable
            logger.debug(f"Could not get image for card, returning zero vector")
            # Get embedding dimension from model (cache it to avoid repeated dummy encoding)
            if not hasattr(self, "_embedding_dim"):
                try:
                    dummy_img = Image.new("RGB", (self.image_size, self.image_size))
                    if self._use_transformers:
                        import torch
                        inputs = self.processor(images=dummy_img, return_tensors="pt")
                        with torch.no_grad():
                            outputs = self.vision_model.get_image_features(**inputs)
                        dummy_emb = outputs[0].cpu().numpy()
                    else:
                        dummy_emb = self.model.encode(dummy_img, convert_to_numpy=True)
                    self._embedding_dim = len(dummy_emb)
                except Exception:
                    # Fallback to common dimension if encoding fails
                    self._embedding_dim = 768 if self._use_transformers else 512
            zero_emb = np.zeros(self._embedding_dim, dtype=np.float32)
            return zero_emb

        # Generate embedding
        if self._use_transformers:
            # SigLIP: Use transformers directly
            import torch
            inputs = self.processor(images=image, return_tensors="pt")
            with torch.no_grad():
                outputs = self.vision_model.get_image_features(**inputs)
            embedding = outputs[0].cpu().numpy()
        else:
            # CLIP: Use sentence-transformers
            embedding = self.model.encode(image, convert_to_numpy=True)

        # Cache it
        self._memory_cache[cache_key] = embedding

        return embedding

    def similarity(
        self,
        card1: dict[str, Any] | str | Image.Image,
        card2: dict[str, Any] | str | Image.Image,
    ) -> float:
        """
        Compute cosine similarity between two card visual embeddings.

        Args:
            card1: First card (dict, name string, or PIL Image)
            card2: Second card (dict, name string, or PIL Image)

        Returns:
            Cosine similarity score in [0, 1]
        """
        emb1 = self.embed_card(card1)
        emb2 = self.embed_card(card2)

        # Cosine similarity
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Cosine similarity is in [-1, 1], map to [0, 1]
        # (similarity + 1.0) / 2.0 maps [-1, 1] -> [0, 1]
        normalized_similarity = (similarity + 1.0) / 2.0

        # Ensure in [0, 1] (should be, but clamp for safety)
        return max(0.0, min(1.0, normalized_similarity))

    def embed_batch(self, cards: list[dict[str, Any] | str | Image.Image]) -> np.ndarray:
        """
        Embed multiple cards efficiently (batch processing).

        Args:
            cards: List of card dicts, names, or PIL Images

        Returns:
            Array of embeddings (n_samples, embedding_dim)
        """
        # Convert cards to images
        images = []
        valid_indices = []

        for i, card in enumerate(cards):
            image = self._card_to_image(card)
            if image is not None:
                images.append(image)
                valid_indices.append(i)
            else:
                logger.debug(f"Skipping card {i} (no image available)")

        if not images:
            # Return zero embeddings
            logger.warning("No valid images found in batch, returning zero embeddings")
            # Get embedding dimension (use cached value if available)
            if not hasattr(self, "_embedding_dim"):
                try:
                    dummy_img = Image.new("RGB", (self.image_size, self.image_size))
                    if self._use_transformers:
                        import torch
                        inputs = self.processor(images=dummy_img, return_tensors="pt")
                        with torch.no_grad():
                            outputs = self.vision_model.get_image_features(**inputs)
                        dummy_emb = outputs[0].cpu().numpy()
                    else:
                        dummy_emb = self.model.encode(dummy_img, convert_to_numpy=True)
                    self._embedding_dim = len(dummy_emb)
                except Exception:
                    self._embedding_dim = 768 if self._use_transformers else 512
            return np.zeros((len(cards), self._embedding_dim), dtype=np.float32)

        # Batch encode (more efficient)
        if self._use_transformers:
            # SigLIP: Use transformers directly with batch processing
            import torch
            inputs = self.processor(images=images, return_tensors="pt")
            with torch.no_grad():
                outputs = self.vision_model.get_image_features(**inputs)
            embeddings = outputs.cpu().numpy()
        else:
            # CLIP: Use sentence-transformers
            embeddings = self.model.encode(images, convert_to_numpy=True, show_progress_bar=False)

        # Update cache and create full result array
        result = np.zeros((len(cards), embeddings.shape[1]), dtype=np.float32)
        for idx, valid_idx in enumerate(valid_indices):
            card = cards[valid_idx]
            cache_key = self._get_cache_key(card)
            self._memory_cache[cache_key] = embeddings[idx]
            result[valid_idx] = embeddings[idx]

        return result

    def save_cache(self) -> None:
        """Explicitly save cache to disk."""
        self._save_cache()

    def __del__(self):
        """Save cache on destruction."""
        try:
            self._save_cache()
        except Exception:
            pass


# Global instance (lazy initialization)
_global_visual_embedder: CardVisualEmbedder | None = None


def get_visual_embedder(
    model_name: str = "google/siglip-base-patch16-224",  # SigLIP (better performance, patched)
    cache_dir: Path | str | None = None,
    image_cache_dir: Path | str | None = None,
) -> CardVisualEmbedder:
    """
    Get or create global visual embedder instance.

    Args:
        model_name: Model to use
        cache_dir: Cache directory for embeddings
        image_cache_dir: Cache directory for images

    Returns:
        CardVisualEmbedder instance
    """
    global _global_visual_embedder

    if _global_visual_embedder is None:
        _global_visual_embedder = CardVisualEmbedder(
            model_name=model_name, cache_dir=cache_dir, image_cache_dir=image_cache_dir
        )

    return _global_visual_embedder


__all__ = ["CardVisualEmbedder", "get_visual_embedder"]

