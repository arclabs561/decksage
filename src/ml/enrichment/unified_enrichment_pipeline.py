#!/usr/bin/env python3
"""
Unified Enrichment Pipeline

Orchestrates all enrichment strategies:
1. Rule-based functional tagging (fast, deterministic, free)
2. LLM semantic analysis (moderate cost, high abstraction)
3. Vision analysis (expensive, art/visual features)

Smart defaults:
- Always run rule-based (free)
- Run LLM on sample or meta-relevant cards
- Run vision on representative sample only

Cost-aware and efficient.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum


class EnrichmentLevel(Enum):
    """Enrichment thoroughness levels"""
    BASIC = "basic"  # Rule-based only (free)
    STANDARD = "standard"  # Rule-based + LLM sample (low cost)
    COMPREHENSIVE = "comprehensive"  # Rule-based + LLM all + vision sample (moderate cost)
    FULL = "full"  # Everything on everything (expensive!)


@dataclass
class UnifiedCardFeatures:
    """Combined features from all enrichment methods"""
    card_name: str
    game: str
    
    # Rule-based (always present)
    functional_tags: dict
    
    # LLM semantic (optional)
    semantic_features: Optional[dict] = None
    
    # Vision (optional)
    vision_features: Optional[dict] = None
    
    # Meta
    enrichment_level: str = "basic"
    total_cost_usd: float = 0.0


class UnifiedEnrichmentPipeline:
    """Orchestrates all enrichment strategies"""
    
    def __init__(self, game: str, level: EnrichmentLevel = EnrichmentLevel.STANDARD):
        self.game = game
        self.level = level
        
        # Initialize rule-based tagger (always)
        self._init_rule_tagger()
        
        # Initialize LLM enricher (if needed)
        self.llm_enricher = None
        if level in [EnrichmentLevel.STANDARD, EnrichmentLevel.COMPREHENSIVE, EnrichmentLevel.FULL]:
            try:
                from .llm_semantic_enricher import LLMSemanticEnricher
                self.llm_enricher = LLMSemanticEnricher()
                print("✓ LLM enricher initialized")
            except Exception as e:
                print(f"⚠️  LLM enricher unavailable: {e}")
        
        # Initialize vision enricher (if needed)
        self.vision_enricher = None
        if level in [EnrichmentLevel.COMPREHENSIVE, EnrichmentLevel.FULL]:
            try:
                from .vision_card_enricher import VisionCardEnricher
                self.vision_enricher = VisionCardEnricher()
                print("✓ Vision enricher initialized")
            except Exception as e:
                print(f"⚠️  Vision enricher unavailable: {e}")
    
    def _init_rule_tagger(self):
        """Initialize game-specific rule tagger"""
        try:
            if self.game == "mtg":
                from .card_functional_tagger import FunctionalTagger
                self.rule_tagger = FunctionalTagger()
            elif self.game == "pokemon":
                from .pokemon_functional_tagger import PokemonFunctionalTagger
                self.rule_tagger = PokemonFunctionalTagger()
            elif self.game == "yugioh":
                from .yugioh_functional_tagger import YugiohFunctionalTagger
                self.rule_tagger = YugiohFunctionalTagger()
            else:
                raise ValueError(f"Unknown game: {self.game}")
            
            print(f"✓ Rule-based tagger initialized for {self.game}")
        except ImportError as e:
            # Handle case where module path needs adjustment
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            if self.game == "mtg":
                from .card_functional_tagger import FunctionalTagger
                self.rule_tagger = FunctionalTagger()
            elif self.game == "pokemon":
                from .pokemon_functional_tagger import PokemonFunctionalTagger
                self.rule_tagger = PokemonFunctionalTagger()
            elif self.game == "yugioh":
                from .yugioh_functional_tagger import YugiohFunctionalTagger
                self.rule_tagger = YugiohFunctionalTagger()
            print(f"✓ Rule-based tagger initialized for {self.game}")
    
    def enrich_card(self, card_data: dict, include_vision: bool = False) -> UnifiedCardFeatures:
        """Enrich a single card"""
        
        card_name = card_data.get("name", "")
        cost = 0.0
        
        # 1. Rule-based (always, free)
        if self.game == "mtg":
            functional_tags = self.rule_tagger.tag_card(card_name)
        else:
            functional_tags = self.rule_tagger.tag_card(card_data)
        
        # 2. LLM semantic (optional)
        semantic_features = None
        if self.llm_enricher:
            try:
                semantic = self.llm_enricher.enrich_card(card_data, self.game)
                semantic_features = asdict(semantic)
                cost += 0.002  # Rough estimate per card
            except Exception as e:
                print(f"  LLM enrichment failed for {card_name}: {e}")
        
        # 3. Vision (optional, expensive)
        vision_features = None
        if include_vision and self.vision_enricher:
            image_url = self._get_image_url(card_data)
            if image_url:
                try:
                    vision = self.vision_enricher.enrich_from_url(card_name, image_url)
                    vision_features = asdict(vision)
                    cost += 0.01  # Rough estimate per image
                except Exception as e:
                    print(f"  Vision enrichment failed for {card_name}: {e}")
        
        return UnifiedCardFeatures(
            card_name=card_name,
            game=self.game,
            functional_tags=asdict(functional_tags),
            semantic_features=semantic_features,
            vision_features=vision_features,
            enrichment_level=self.level.value,
            total_cost_usd=cost
        )
    
    def enrich_dataset(self, cards_data: List[dict], output_path: Path, resume: bool = True) -> List[UnifiedCardFeatures]:
        """Enrich entire dataset with smart sampling
        
        Args:
            cards_data: List of card dictionaries
            output_path: Where to save results
            resume: If True, skip cards already in output_path
        """
        
        # Input validation
        if not cards_data:
            raise ValueError("cards_data is empty")
        
        print(f"\n{'='*60}")
        print(f"Unified Enrichment Pipeline - {self.level.value.upper()}")
        print(f"Game: {self.game.upper()}")
        print(f"Cards: {len(cards_data)}")
        print(f"{'='*60}\n")
        
        results = []
        total_cost = 0.0
        
        # Resume capability: Load existing results if they exist
        processed_names = set()
        if resume and output_path.exists():
            try:
                with open(output_path) as f:
                    existing_results = json.load(f)
                    results = existing_results
                    processed_names = {r["card_name"] for r in existing_results}
                    print(f"📁 Resuming: Found {len(processed_names)} already processed cards\n")
            except Exception as e:
                print(f"⚠️  Could not resume from {output_path}: {e}\n")
        
        # Determine sampling strategy
        if self.level == EnrichmentLevel.BASIC:
            # Rule-based only, all cards
            llm_sample = []
            vision_sample = []
        
        elif self.level == EnrichmentLevel.STANDARD:
            # LLM on sample (100 cards), no vision
            llm_sample = self._sample_cards(cards_data, 100)
            vision_sample = []
        
        elif self.level == EnrichmentLevel.COMPREHENSIVE:
            # LLM on all, vision on sample (50 cards)
            llm_sample = cards_data
            vision_sample = self._sample_cards(cards_data, 50)
        
        elif self.level == EnrichmentLevel.FULL:
            # Everything on everything
            llm_sample = cards_data
            vision_sample = cards_data
        
        print(f"Strategy:")
        print(f"  Rule-based: {len(cards_data)} cards (free)")
        print(f"  LLM: {len(llm_sample)} cards (~${len(llm_sample)*0.002:.2f})")
        print(f"  Vision: {len(vision_sample)} cards (~${len(vision_sample)*0.01:.2f})")
        print(f"  Estimated total: ~${len(llm_sample)*0.002 + len(vision_sample)*0.01:.2f}\n")
        
        # PERFORMANCE: Convert to sets for O(1) lookup instead of O(n)
        llm_sample_names = {c.get("name", "") for c in llm_sample}
        vision_sample_names = {c.get("name", "") for c in vision_sample}
        
        # Process cards
        skipped = 0
        for i, card_data in enumerate(cards_data):
            card_name = card_data.get("name", "Unknown")
            
            # Skip if already processed (resume capability)
            if card_name in processed_names:
                skipped += 1
                continue
            
            # Determine if this card gets LLM/vision (O(1) lookup)
            include_llm = card_name in llm_sample_names
            include_vision = card_name in vision_sample_names
            
            # Temporarily disable enrichers if not needed for this card
            orig_llm = self.llm_enricher
            orig_vision = self.vision_enricher
            
            if not include_llm:
                self.llm_enricher = None
            if not include_vision:
                self.vision_enricher = None
            
            try:
                features = self.enrich_card(card_data, include_vision=include_vision)
                results.append(asdict(features))
                total_cost += features.total_cost_usd
                
                # Progress reporting and incremental saves
                if (i + 1) % 100 == 0:
                    print(f"  Processed {i+1}/{len(cards_data)} cards...")
                    # Incremental save every 100 cards (avoid losing progress)
                    with open(output_path, "w") as f:
                        json.dump(results, f, indent=2)
            
            except Exception as e:
                print(f"  ✗ {card_name}: {e}")
                # Continue processing even if one card fails
            
            # Restore enrichers
            self.llm_enricher = orig_llm
            self.vision_enricher = orig_vision
        
        # Save results
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        print(f"\n{'='*60}")
        print(f"✅ Enrichment Complete")
        print(f"  Total cards: {len(results)}")
        print(f"  Processed: {len(results) - len(processed_names)} new")
        print(f"  Skipped: {skipped} (already done)")
        print(f"  With LLM: {sum(1 for r in results if r.get('semantic_features'))}")
        print(f"  With vision: {sum(1 for r in results if r.get('vision_features'))}")
        print(f"  Errors: {len(cards_data) - len(results)}")
        print(f"  Actual cost: ${total_cost:.2f}")
        print(f"  Saved to: {output_path}")
        print(f"{'='*60}\n")
        
        return results
    
    def _sample_cards(self, cards: List[dict], n: int) -> List[dict]:
        """Sample N cards intelligently"""
        from .vision_card_enricher import SmartCardSampler
        return SmartCardSampler.sample_diverse_cards(cards, n)
    
    def _get_image_url(self, card_data: dict) -> Optional[str]:
        """Extract image URL from card data"""
        
        # MTG
        if "images" in card_data and card_data["images"]:
            return card_data["images"][0].get("url", "")
        
        # Pokemon
        if "images" in card_data and isinstance(card_data["images"], list) and card_data["images"]:
            return card_data["images"][0].get("large", "") or card_data["images"][0].get("url", "")
        
        # YGO
        if "images" in card_data and isinstance(card_data["images"], list) and card_data["images"]:
            return card_data["images"][0].get("url", "")
        
        return None


# CLI interface
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified Card Enrichment Pipeline")
    parser.add_argument("--game", required=True, choices=["mtg", "pokemon", "yugioh"], help="Card game")
    parser.add_argument("--input", required=True, help="Input cards JSON file")
    parser.add_argument("--output", required=True, help="Output enriched JSON file")
    parser.add_argument("--level", default="standard", choices=["basic", "standard", "comprehensive", "full"],
                       help="Enrichment level (default: standard)")
    
    args = parser.parse_args()
    
    # Load cards
    with open(args.input) as f:
        cards_data = json.load(f)
    
    # Run pipeline
    level = EnrichmentLevel(args.level)
    pipeline = UnifiedEnrichmentPipeline(args.game, level)
    
    results = pipeline.enrich_dataset(cards_data, Path(args.output))
    
    print(f"Done! Results saved to {args.output}")


if __name__ == "__main__":
    # Example usage
    print("Unified Enrichment Pipeline")
    print("\nEnrichment Levels:")
    print("  basic: Rule-based only (free)")
    print("  standard: Rule-based + LLM sample (~$0.20)")
    print("  comprehensive: Rule-based all + LLM all + Vision sample (~$2-5)")
    print("  full: Everything (expensive!)")
    print("\nRun with: python unified_enrichment_pipeline.py --game mtg --input cards.json --output enriched.json --level standard")
