#!/usr/bin/env python3
"""
Scryfall API utilities for fetching card image URLs.

Integrates with card attribute enrichment pipeline.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("decksage.scryfall")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests not installed. Install with: uv add requests")


def get_scryfall_image_url(
    card_name: str,
    retry_delay: float = 0.1,
    max_retries: int = 3,
) -> str | None:
    """
    Get image URL from Scryfall API for a card name.
    
    Args:
        card_name: Card name to look up (exact match)
        retry_delay: Delay between API calls (Scryfall rate limit: 50-100ms)
        max_retries: Maximum retry attempts for failed requests
    
    Returns:
        Image URL (PNG preferred) or None if not found
    """
    if not HAS_REQUESTS:
        logger.warning("requests library required for Scryfall API")
        return None
    
    url = "https://api.scryfall.com/cards/named"
    params = {"exact": card_name, "format": "json"}
    headers = {"User-Agent": "DeckSage/1.0 (https://decksage.com)"}
    
    for attempt in range(max_retries):
        try:
            time.sleep(retry_delay)  # Rate limiting
            response = requests.get(url, params=params, timeout=10, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract image URL (prefer PNG, fallback to large/normal)
            if "image_uris" in data:
                image_uris = data["image_uris"]
                return image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")
            
            # Handle multi-faced cards (DFCs)
            if "card_faces" in data and len(data["card_faces"]) > 0:
                face = data["card_faces"][0]
                if "image_uris" in face:
                    image_uris = face["image_uris"]
                    return image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")
            
            return None
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug(f"Card not found in Scryfall: {card_name}")
                return None
            if attempt < max_retries - 1:
                logger.debug(f"HTTP error for {card_name} (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.warning(f"HTTP error for {card_name} after {max_retries} attempts: {e}")
                return None
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                logger.debug(f"Timeout fetching {card_name} (attempt {attempt + 1}/{max_retries})")
                time.sleep(2 ** attempt)
            else:
                logger.warning(f"Timeout fetching {card_name} after {max_retries} attempts")
                return None
        except Exception as e:
            if attempt < max_retries - 1:
                logger.debug(f"Error fetching {card_name} (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(2 ** attempt)
            else:
                logger.warning(f"Error fetching {card_name} after {max_retries} attempts: {e}")
                return None
    
    return None


def enrich_card_attributes_with_images(
    card_attributes: dict[str, dict[str, Any]],
    batch_size: int = 50,
    resume: bool = True,
) -> dict[str, Any]:
    """
    Enrich card attributes dict with image URLs from Scryfall.
    
    Modifies card_attributes in-place, adding 'image_url' field to each card.
    
    Args:
        card_attributes: Dict mapping card name -> card attributes dict
        batch_size: Progress reporting interval
        resume: If True, skip cards that already have image_url
    
    Returns:
        Statistics dict with fetched, failed, already_had counts
    """
    if not HAS_REQUESTS:
        logger.warning("requests library required")
        return {"error": "Missing dependencies"}
    
    fetched = 0
    failed = 0
    already_had = 0
    
    cards_to_process = []
    for card_name, attrs in card_attributes.items():
        if resume and attrs.get("image_url"):
            already_had += 1
            continue
        cards_to_process.append((card_name, attrs))
    
    logger.info(f"Fetching image URLs for {len(cards_to_process)} cards...")
    logger.info(f"  (This will take ~{len(cards_to_process) * 0.1 / 60:.1f} minutes due to rate limiting)")
    
    for i, (card_name, attrs) in enumerate(cards_to_process):
        image_url = get_scryfall_image_url(card_name)
        
        if image_url:
            attrs["image_url"] = image_url
            fetched += 1
        else:
            failed += 1
        
        if (i + 1) % batch_size == 0:
            logger.info(f"  Progress: {i + 1}/{len(cards_to_process)} ({fetched} fetched, {failed} failed)")
    
    logger.info(f"  Complete: {fetched} fetched, {failed} failed, {already_had} already had URLs")
    
    return {
        "total": len(card_attributes),
        "fetched": fetched,
        "failed": failed,
        "already_had": already_had,
        "with_images": sum(1 for attrs in card_attributes.values() if attrs.get("image_url")),
    }


__all__ = ["get_scryfall_image_url", "enrich_card_attributes_with_images"]

