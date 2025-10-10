#!/usr/bin/env python3
"""
LLM-Based Semantic Card Enricher

Uses LLMs to extract abstract features that rule-based taggers miss:
- Strategic archetypes (combo, control, aggro, midrange)
- Synergy descriptions (what this card works well with)
- Meta-game positioning (why this card is played)
- Skill ceiling/floor (complexity rating)
- Flavor/strategy text (human-readable descriptions)

Uses OpenRouter API for cost-effective access to multiple LLMs.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

# Rate limiting: Max 60 requests per minute (OpenRouter limit)
_last_request_time = 0
_min_request_interval = 1.0  # 1 second between requests


@dataclass
class SemanticCardFeatures:
    """LLM-extracted semantic features"""
    card_name: str
    game: str  # mtg, pokemon, yugioh
    
    # Strategic classification
    archetype_role: str  # combo, control, aggro, midrange, tempo, ramp
    play_pattern: str  # early-game, mid-game, late-game, all-game
    complexity: int  # 1-5 (1=simple, 5=complex)
    
    # Synergy analysis
    synergies: List[str]  # Card names that synergize
    anti_synergies: List[str]  # Cards that conflict
    archetype_fit: List[str]  # Deck archetypes this fits
    
    # Meta-game
    meta_relevance: int  # 1-5 (1=niche, 5=meta-defining)
    power_level: int  # 1-5 (1=weak, 5=strong)
    format_staple: bool  # Is this a format staple?
    
    # Human-readable
    strategy_summary: str  # One sentence strategy
    synergy_explanation: str  # Why it synergizes with X
    weakness_explanation: str  # Vulnerabilities
    
    # Advanced
    win_condition: bool  # Is this a win condition?
    enabler: bool  # Enables strategies (not win con itself)
    tech_card: bool  # Counter-meta tech card
    
    # Confidence
    llm_confidence: float  # 0-1, how confident the LLM is


class LLMSemanticEnricher:
    """Uses LLMs to extract semantic card features"""
    
    def __init__(self, api_key: str = None, model: str = "anthropic/claude-4.5-sonnet"):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def enrich_card(self, card_data: dict, game: str) -> SemanticCardFeatures:
        """Extract semantic features for a card using LLM"""
        
        card_name = card_data.get("name", "")
        
        # Build prompt based on game
        prompt = self._build_prompt(card_data, game)
        
        # Call LLM
        response = self._call_llm(prompt)
        
        # Parse response
        features = self._parse_response(response, card_name, game)
        
        return features
    
    def _build_prompt(self, card_data: dict, game: str) -> str:
        """Build game-specific prompt"""
        
        card_name = card_data.get("name", "Unknown")
        
        if game == "mtg":
            oracle_text = ""
            if "faces" in card_data and card_data["faces"]:
                oracle_text = card_data["faces"][0].get("oracle_text", "")
            elif "oracle_text" in card_data:
                oracle_text = card_data["oracle_text"]
            
            type_line = ""
            if "faces" in card_data and card_data["faces"]:
                type_line = card_data["faces"][0].get("type_line", "")
            elif "type_line" in card_data:
                type_line = card_data["type_line"]
            
            mana_cost = ""
            if "faces" in card_data and card_data["faces"]:
                mana_cost = card_data["faces"][0].get("mana_cost", "")
            elif "mana_cost" in card_data:
                mana_cost = card_data["mana_cost"]
            
            prompt = f"""Analyze this Magic: The Gathering card for semantic features.

Card: {card_name}
Type: {type_line}
Mana Cost: {mana_cost}
Text: {oracle_text}

Extract semantic features in JSON format:
{{
  "archetype_role": "combo|control|aggro|midrange|tempo|ramp",
  "play_pattern": "early-game|mid-game|late-game|all-game",
  "complexity": 1-5,
  "synergies": ["card names that synergize"],
  "anti_synergies": ["cards that conflict"],
  "archetype_fit": ["deck archetypes this fits"],
  "meta_relevance": 1-5,
  "power_level": 1-5,
  "format_staple": true/false,
  "strategy_summary": "one sentence strategy",
  "synergy_explanation": "why it synergizes",
  "weakness_explanation": "vulnerabilities",
  "win_condition": true/false,
  "enabler": true/false,
  "tech_card": true/false,
  "llm_confidence": 0-1
}}

Focus on strategic depth, not just literal card text."""
        
        elif game == "pokemon":
            hp = card_data.get("hp", "")
            attacks = card_data.get("attacks", [])
            abilities = card_data.get("abilities", [])
            
            attacks_text = "\n".join([f"  - {a.get('name', '')}: {a.get('damage', '')} damage. {a.get('text', '')}" for a in attacks])
            abilities_text = "\n".join([f"  - {a.get('name', '')}: {a.get('text', '')}" for a in abilities])
            
            prompt = f"""Analyze this Pokemon TCG card for semantic features.

Card: {card_name}
HP: {hp}

Attacks:
{attacks_text}

Abilities:
{abilities_text}

Extract semantic features in JSON format (same schema as above).

Focus on competitive play patterns, energy requirements, and meta positioning."""
        
        elif game == "yugioh":
            card_type = card_data.get("type", "")
            # YGO API uses "desc" or "description"
            desc = card_data.get("desc", "") or card_data.get("description", "")
            atk = card_data.get("atk", card_data.get("ATK", ""))
            def_val = card_data.get("def", card_data.get("DEF", ""))
            
            prompt = f"""Analyze this Yu-Gi-Oh! card for semantic features.

Card: {card_name}
Type: {card_type}
ATK/DEF: {atk}/{def_val}
Effect: {desc}

Extract semantic features in JSON format (same schema as above).

Focus on hand trap potential, floodgate effects, combo pieces, and meta relevance."""
        
        else:
            raise ValueError(f"Unknown game: {game}")
        
        return prompt
    
    def _call_llm(self, prompt: str, temperature: float = 0.3) -> str:
        """Call OpenRouter API with rate limiting"""
        
        # Attempt application-level cache first
        try:
            from utils.llm_cache import LLMCache, cached_call, make_openrouter_payload  # type: ignore
        except Exception:  # pragma: no cover
            LLMCache = None  # type: ignore
            cached_call = None  # type: ignore

        def _compute_http() -> str:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/decksage",
                "X-Title": "DeckSage Card Enrichment"
            }
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert card game analyst. Extract semantic features from cards in JSON format. Be concise and accurate."
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": 1000,
            }
            try:
                response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
                _last_request_time = time.time()  # noqa: F841 - local rate counter
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except requests.exceptions.Timeout:
                print(f"Error: LLM request timed out after 30s")
                return "{}"
            except requests.exceptions.HTTPError as e:
                print(f"Error: HTTP {e.response.status_code} from LLM API")
                return "{}"
            except Exception as e:
                print(f"Error calling LLM: {e}")
                return "{}"

        # Build deterministic key
        cache_payload = make_openrouter_payload(
            self.model,
            [
                {"role": "system", "content": "You are an expert card game analyst. Extract semantic features from cards in JSON format. Be concise and accurate."},
                {"role": "user", "content": prompt},
            ],
            params={"temperature": temperature, "max_tokens": 1000},
        ) if 'make_openrouter_payload' in globals() else None

        if LLMCache is not None and cache_payload is not None:
            try:
                cache = LLMCache(scope="llm_enricher")
                return cached_call(cache, cache_payload, _compute_http)
            except Exception:
                pass

        # No cache available
        
        return _compute_http()
    
    def _parse_response(self, response: str, card_name: str, game: str) -> SemanticCardFeatures:
        """Parse LLM response into structured features"""
        
        try:
            # Extract JSON from markdown if wrapped in ```json
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            # Handle multiline JSON or additional text after JSON
            # Find first { and last }
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                response = response[start:end+1]
            
            data = json.loads(response)
            
            return SemanticCardFeatures(
                card_name=card_name,
                game=game,
                archetype_role=data.get("archetype_role", "unknown"),
                play_pattern=data.get("play_pattern", "unknown"),
                complexity=data.get("complexity", 3),
                synergies=data.get("synergies", []),
                anti_synergies=data.get("anti_synergies", []),
                archetype_fit=data.get("archetype_fit", []),
                meta_relevance=data.get("meta_relevance", 3),
                power_level=data.get("power_level", 3),
                format_staple=data.get("format_staple", False),
                strategy_summary=data.get("strategy_summary", ""),
                synergy_explanation=data.get("synergy_explanation", ""),
                weakness_explanation=data.get("weakness_explanation", ""),
                win_condition=data.get("win_condition", False),
                enabler=data.get("enabler", False),
                tech_card=data.get("tech_card", False),
                llm_confidence=data.get("llm_confidence", 0.5)
            )
        
        except Exception as e:
            print(f"Error parsing LLM response for {card_name}: {e}")
            # Return default features
            return SemanticCardFeatures(
                card_name=card_name,
                game=game,
                archetype_role="unknown",
                play_pattern="unknown",
                complexity=3,
                synergies=[],
                anti_synergies=[],
                archetype_fit=[],
                meta_relevance=3,
                power_level=3,
                format_staple=False,
                strategy_summary="",
                synergy_explanation="",
                weakness_explanation="",
                win_condition=False,
                enabler=False,
                tech_card=False,
                llm_confidence=0.0
            )
    
    def enrich_batch(self, cards_data: List[dict], game: str, output_path: Path, batch_size: int = 10):
        """Enrich multiple cards in batches (cost-effective)"""
        
        print(f"Enriching {len(cards_data)} cards with LLM analysis...")
        print(f"Model: {self.model}")
        print(f"Estimated cost: ${len(cards_data) * 0.002:.2f} (rough estimate)")
        
        results = []
        
        for i in range(0, len(cards_data), batch_size):
            batch = cards_data[i:i+batch_size]
            
            print(f"\nProcessing batch {i//batch_size + 1}/{(len(cards_data)-1)//batch_size + 1}...")
            
            for card_data in batch:
                try:
                    features = self.enrich_card(card_data, game)
                    results.append(asdict(features))
                    
                    print(f"  ✓ {features.card_name}: {features.archetype_role}, complexity={features.complexity}")
                
                except Exception as e:
                    card_name = card_data.get("name", "Unknown")
                    print(f"  ✗ {card_name}: Error - {e}")
        
        # Save results
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✅ Saved {len(results)} enriched cards to {output_path}")
        
        return results


# Hybrid enricher: combines rule-based + LLM
class HybridEnricher:
    """Combines rule-based functional tagging with LLM semantic analysis"""
    
    def __init__(self, game: str, use_llm: bool = True):
        self.game = game
        self.use_llm = use_llm
        
        # Initialize rule-based taggers
        if game == "mtg":
            from .card_functional_tagger import FunctionalTagger

            self.rule_tagger = FunctionalTagger()
        elif game == "pokemon":
            from .pokemon_functional_tagger import PokemonFunctionalTagger

            self.rule_tagger = PokemonFunctionalTagger()
        elif game == "yugioh":
            from .yugioh_functional_tagger import YugiohFunctionalTagger

            self.rule_tagger = YugiohFunctionalTagger()
        else:
            raise ValueError(f"Unknown game: {game}")
        
        # Initialize LLM enricher
        if use_llm:
            self.llm_enricher = LLMSemanticEnricher()
    
    def enrich_card(self, card_data: dict) -> dict:
        """Get both rule-based and LLM features"""
        
        result = {
            "card_name": card_data.get("name", ""),
            "game": self.game
        }
        
        # Rule-based features (fast, deterministic)
        if self.game == "mtg":
            rule_features = self.rule_tagger.tag_card(card_data.get("name", ""))
        else:
            rule_features = self.rule_tagger.tag_card(card_data)
        
        result["rule_based_features"] = asdict(rule_features)
        
        # LLM features (slow, semantic)
        if self.use_llm:
            llm_features = self.llm_enricher.enrich_card(card_data, self.game)
            result["llm_features"] = asdict(llm_features)
        
        return result


if __name__ == "__main__":
    # Example usage
    enricher = LLMSemanticEnricher()
    
    # Example MTG card
    mtg_card = {
        "name": "Lightning Bolt",
        "faces": [{
            "type_line": "Instant",
            "mana_cost": "{R}",
            "oracle_text": "Lightning Bolt deals 3 damage to any target."
        }]
    }
    
    print("Enriching Lightning Bolt...")
    features = enricher.enrich_card(mtg_card, "mtg")
    
    print(f"\nArchetype Role: {features.archetype_role}")
    print(f"Complexity: {features.complexity}/5")
    print(f"Strategy: {features.strategy_summary}")
    print(f"Synergies: {', '.join(features.synergies[:3])}")
    print(f"Power Level: {features.power_level}/5")
    print(f"Confidence: {features.llm_confidence:.2f}")
