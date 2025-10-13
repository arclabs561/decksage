#!/usr/bin/env python3
"""
Vision-Based Card Enricher

Uses vision-language models (vLLMs) to extract features from card images:
- Art style (realistic, fantasy, abstract, etc.)
- Color palette dominance
- Visual complexity
- Card frame/border features
- Creature type inference from art
- Flavor/mood analysis

Uses OpenRouter's vision models (GPT-4V, Claude 3 with vision, etc.)
"""

import json
import os
import base64
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv
from PIL import Image
import io

load_dotenv()


@dataclass
class VisionCardFeatures:
    """Vision-extracted features from card art"""
    card_name: str
    image_url: str
    
    # Art style
    art_style: str  # realistic, fantasy, abstract, anime, pixel-art, etc.
    art_complexity: int  # 1-5 (1=simple, 5=complex)
    
    # Color analysis
    dominant_colors: List[str]  # ["red", "blue", "gold"]
    color_saturation: str  # high, medium, low
    brightness: str  # bright, neutral, dark
    
    # Composition
    focal_point: str  # center, left, right, top, bottom
    composition_style: str  # portrait, landscape, action, abstract
    
    # Theme/Mood
    mood: str  # aggressive, peaceful, mysterious, chaotic, etc.
    theme: str  # nature, technology, darkness, light, etc.
    
    # Card frame features
    frame_style: str  # modern, retro, special (from detected borders)
    foil_indication: bool  # Visual indicators of foil/special treatment
    
    # Creature/Character analysis (if visible)
    creature_count: int  # Number of creatures visible
    creature_types: List[str]  # ["dragon", "warrior", etc.]
    
    # Text visibility
    text_legible: bool  # Is card text readable in image?
    
    # Overall
    visual_impact: int  # 1-5 (memorability/distinctiveness)
    llm_confidence: float  # 0-1


class VisionCardEnricher:
    """Uses vision LLMs to analyze card images"""
    
    def __init__(self, api_key: str = None, model: str = "anthropic/claude-4.5-sonnet"):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        self.model = model  # Vision-capable model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def enrich_from_url(self, card_name: str, image_url: str) -> VisionCardFeatures:
        """Analyze card from image URL"""
        
        prompt = """Analyze this trading card game card image and extract visual features in JSON format:

{
  "art_style": "realistic|fantasy|abstract|anime|pixel-art|painterly",
  "art_complexity": 1-5,
  "dominant_colors": ["color1", "color2", "color3"],
  "color_saturation": "high|medium|low",
  "brightness": "bright|neutral|dark",
  "focal_point": "center|left|right|top|bottom",
  "composition_style": "portrait|landscape|action|abstract",
  "mood": "aggressive|peaceful|mysterious|chaotic|epic|etc",
  "theme": "nature|technology|darkness|light|fire|water|etc",
  "frame_style": "modern|retro|special",
  "foil_indication": true/false,
  "creature_count": 0-5+,
  "creature_types": ["dragon", "warrior", etc],
  "text_legible": true/false,
  "visual_impact": 1-5,
  "llm_confidence": 0-1
}

Focus on art analysis, not game mechanics."""
        
        response = self._call_vision_llm(prompt, image_url)
        features = self._parse_response(response, card_name, image_url)
        
        return features
    
    def enrich_from_file(self, card_name: str, image_path: Path) -> VisionCardFeatures:
        """Analyze card from local image file"""
        
        # Convert local file to base64
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # Get image format
        img = Image.open(image_path)
        format_str = img.format.lower() if img.format else "jpeg"
        
        data_url = f"data:image/{format_str};base64,{base64_image}"
        
        return self.enrich_from_url(card_name, data_url)
    
    def _call_vision_llm(self, prompt: str, image_url: str) -> str:
        """Call OpenRouter vision API"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/decksage",
            "X-Title": "DeckSage Vision Enrichment"
        }
        
        # Vision API format
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.3,
            "max_tokens": 800
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            return content
        
        except Exception as e:
            print(f"Error calling vision LLM: {e}")
            return "{}"
    
    def _parse_response(self, response: str, card_name: str, image_url: str) -> VisionCardFeatures:
        """Parse vision LLM response"""
        
        try:
            # Extract JSON
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            data = json.loads(response)
            
            return VisionCardFeatures(
                card_name=card_name,
                image_url=image_url,
                art_style=data.get("art_style", "unknown"),
                art_complexity=data.get("art_complexity", 3),
                dominant_colors=data.get("dominant_colors", []),
                color_saturation=data.get("color_saturation", "medium"),
                brightness=data.get("brightness", "neutral"),
                focal_point=data.get("focal_point", "center"),
                composition_style=data.get("composition_style", "portrait"),
                mood=data.get("mood", "neutral"),
                theme=data.get("theme", "unknown"),
                frame_style=data.get("frame_style", "modern"),
                foil_indication=data.get("foil_indication", False),
                creature_count=data.get("creature_count", 0),
                creature_types=data.get("creature_types", []),
                text_legible=data.get("text_legible", True),
                visual_impact=data.get("visual_impact", 3),
                llm_confidence=data.get("llm_confidence", 0.5)
            )
        
        except Exception as e:
            print(f"Error parsing vision response for {card_name}: {e}")
            return VisionCardFeatures(
                card_name=card_name,
                image_url=image_url,
                art_style="unknown",
                art_complexity=3,
                dominant_colors=[],
                color_saturation="medium",
                brightness="neutral",
                focal_point="center",
                composition_style="portrait",
                mood="neutral",
                theme="unknown",
                frame_style="modern",
                foil_indication=False,
                creature_count=0,
                creature_types=[],
                text_legible=True,
                visual_impact=3,
                llm_confidence=0.0
            )
    
    def enrich_batch(self, cards_with_images: List[Dict], output_path: Path, batch_size: int = 5):
        """Enrich multiple cards (expensive! Use sparingly)"""
        
        print(f"Enriching {len(cards_with_images)} card images with vision models...")
        print(f"Model: {self.model}")
        print(f"⚠️  Estimated cost: ${len(cards_with_images) * 0.01:.2f} (vision models are expensive!)")
        print("Consider sampling representative cards rather than full dataset.")
        
        proceed = input("Proceed? (y/n): ")
        if proceed.lower() != 'y':
            print("Aborted.")
            return []
        
        results = []
        
        for i, card_info in enumerate(cards_with_images):
            card_name = card_info.get("name", "Unknown")
            image_url = card_info.get("image_url", "")
            
            if not image_url:
                print(f"  ⊘ {card_name}: No image URL")
                continue
            
            try:
                features = self.enrich_from_url(card_name, image_url)
                results.append(asdict(features))
                
                print(f"  ✓ {card_name}: {features.art_style}, mood={features.mood}, impact={features.visual_impact}/5")
            
            except Exception as e:
                print(f"  ✗ {card_name}: Error - {e}")
            
            # Rate limiting
            if (i + 1) % batch_size == 0:
                print(f"\nProcessed {i+1}/{len(cards_with_images)}. Pausing...")
                import time
                time.sleep(2)  # Avoid rate limits
        
        # Save results
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✅ Saved {len(results)} vision-enriched cards to {output_path}")
        
        return results


# Smart sampler: select diverse cards for vision analysis
class SmartCardSampler:
    """Select representative cards for expensive vision analysis"""
    
    @staticmethod
    def sample_diverse_cards(cards: List[dict], n: int = 100) -> List[dict]:
        """Sample N diverse cards for vision analysis
        
        Strategy:
        - Sample from different rarities
        - Sample from different colors/types
        - Sample popular/meta cards
        - Sample visually distinctive cards
        """
        
        import random
        
        # Prioritize cards with unique names (avoid duplicates)
        unique_cards = {}
        for card in cards:
            name = card.get("name", "")
            if name and name not in unique_cards:
                unique_cards[name] = card
        
        cards = list(unique_cards.values())
        
        # Sample by rarity (if available)
        by_rarity = {}
        for card in cards:
            rarity = card.get("rarity", "common").lower()
            if rarity not in by_rarity:
                by_rarity[rarity] = []
            by_rarity[rarity].append(card)
        
        # Take proportional samples
        samples = []
        rarities = ["mythic", "rare", "uncommon", "common"]
        per_rarity = n // len(rarities)
        
        for rarity in rarities:
            if rarity in by_rarity:
                rarity_cards = by_rarity[rarity]
                sample_size = min(per_rarity, len(rarity_cards))
                samples.extend(random.sample(rarity_cards, sample_size))
        
        # Fill remaining with random
        remaining = n - len(samples)
        if remaining > 0:
            other_cards = [c for c in cards if c not in samples]
            if other_cards:
                samples.extend(random.sample(other_cards, min(remaining, len(other_cards))))
        
        print(f"Sampled {len(samples)} diverse cards from {len(cards)} total")
        return samples[:n]


if __name__ == "__main__":
    # Example usage
    enricher = VisionCardEnricher()
    
    # Example: Analyze a card from Scryfall
    card_name = "Lightning Bolt"
    image_url = "https://cards.scryfall.io/large/front/f/2/f29ba16f-c8fb-42fe-aabf-87089cb214a7.jpg"
    
    print(f"Analyzing {card_name} art...")
    try:
        features = enricher.enrich_from_url(card_name, image_url)
        
        print(f"\nArt Style: {features.art_style}")
        print(f"Dominant Colors: {', '.join(features.dominant_colors)}")
        print(f"Mood: {features.mood}")
        print(f"Theme: {features.theme}")
        print(f"Visual Impact: {features.visual_impact}/5")
        print(f"Confidence: {features.llm_confidence:.2f}")
    except Exception as e:
        print(f"Error: {e}")
        print("Note: Vision enrichment requires valid API key and can be expensive")
