#!/usr/bin/env python3
"""
Minimal stub FunctionalTagger for tests.

Provides a deterministic tagger with a small rule set.
"""

from __future__ import annotations


class FunctionalTagger:
    class Tags:
        def __init__(self, card_name: str):
            self.card_name = card_name
            name = card_name.lower()
            self.removal = any(k in name for k in ["bolt", "shock", "kill"])  # mtg
            self.draw = any(k in name for k in ["draw", "research"])  # generic
            self.ramp = any(k in name for k in ["ramp", "growth"])  # generic

    def tag_card(self, name: str) -> "FunctionalTagger.Tags":
        return FunctionalTagger.Tags(name)

#!/usr/bin/env python3
"""
Card Functional Tagging System

Assigns functional roles/tags to cards based on their oracle text and mechanics.
This provides semantic enrichment beyond co-occurrence data.

Functional roles:
- Removal (creature, artifact, enchantment, planeswalker, land, any permanent)
- Card Draw / Card Advantage
- Ramp (mana acceleration)
- Counterspells
- Tutors (search library)
- Board Wipes / Mass Removal
- Recursion (graveyard retrieval)
- Protection (hexproof, indestructible, ward)
- Evasion (flying, unblockable, etc.)
- Win Conditions (combo pieces, alt-win-cons)
- Hate Cards (specific hosers)
"""

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List
import subprocess


@dataclass
class FunctionalTags:
    """Functional classification for a card"""
    card_name: str
    
    # Removal types
    creature_removal: bool = False
    artifact_removal: bool = False
    enchantment_removal: bool = False
    planeswalker_removal: bool = False
    land_removal: bool = False
    any_permanent_removal: bool = False
    
    # Resource generation
    card_draw: bool = False
    card_advantage: bool = False  # Broader than draw (e.g. impulse draw, card selection)
    ramp: bool = False
    mana_ritual: bool = False  # One-time mana boost
    
    # Interaction
    counterspell: bool = False
    discard: bool = False
    mill: bool = False
    
    # Search/Tutors
    tutor: bool = False
    tutor_creature: bool = False
    tutor_instant_sorcery: bool = False
    tutor_artifact: bool = False
    tutor_enchantment: bool = False
    tutor_land: bool = False
    
    # Board control
    board_wipe: bool = False
    stax: bool = False  # Resource denial
    pillowfort: bool = False  # Damage prevention
    
    # Graveyard
    recursion: bool = False  # Return from graveyard
    reanimation: bool = False  # Specifically creatures
    graveyard_hate: bool = False
    
    # Protection
    protection: bool = False
    hexproof: bool = False
    indestructible: bool = False
    ward: bool = False
    
    # Combat/Evasion
    evasion: bool = False
    flying: bool = False
    unblockable: bool = False
    menace: bool = False
    
    # Win conditions
    win_condition: bool = False
    combo_piece: bool = False
    alt_win_con: bool = False
    
    # Utility
    token_generator: bool = False
    plus_one_counter: bool = False  # +1/+1 counters
    life_gain: bool = False
    life_loss: bool = False
    sacrifice_outlet: bool = False
    
    # Hate cards
    tribal_hate: bool = False
    color_hate: bool = False
    artifact_hate: bool = False
    graveyard_hate_strong: bool = False  # Rest in Peace level


class FunctionalTagger:
    """Tags cards with functional roles based on rules"""
    
    def __init__(self):
        self.card_db = self._load_card_database()
    
    def _load_card_database(self) -> Dict[str, Dict]:
        """Load card database with oracle text"""
        # Try to load from build_card_db.py output
        db_path = Path("scryfall_card_db.json")
        if db_path.exists():
            with open(db_path) as f:
                return json.load(f)
        
        # Otherwise build it
        print("Building card database...")
        try:
            # subprocess.run(
            #     ["uv", "run", "python", "../data/build_card_db.py"],
            #     check=True,
            #     cwd=Path(__file__).parent,
            # )
            # with open(db_path) as f:
            #     return json.load(f)
            print("Warning: build_card_db.py not found. Using empty card DB.")
            return {}
        except Exception as e:
            print(f"Warning: Could not load card database: {e}")
            return {}
    
    def tag_card(
        self, card_name: str, oracle_text: str = None, type_line: str = None
    ) -> FunctionalTags:
        """Tag a card with functional roles"""
        tags = FunctionalTags(card_name=card_name)
        
        # Get card data
        card_data = self.card_db.get(card_name, {})
        if oracle_text is None:
            oracle_text = card_data.get("oracle_text", "")
        if type_line is None:
            type_line = card_data.get("type_line", "")
        
        oracle_lower = oracle_text.lower()
        type_lower = type_line.lower()
        
        # Removal detection
        tags.creature_removal = self._has_creature_removal(oracle_lower, type_lower)
        tags.artifact_removal = self._has_artifact_removal(oracle_lower)
        tags.enchantment_removal = self._has_enchantment_removal(oracle_lower)
        tags.planeswalker_removal = self._has_planeswalker_removal(
            oracle_lower, tags.creature_removal
        )
        tags.land_removal = self._has_land_removal(oracle_lower)
        tags.any_permanent_removal = self._has_any_permanent_removal(oracle_lower)
        
        # Resource generation
        tags.card_draw = self._has_card_draw(oracle_lower)
        tags.card_advantage = tags.card_draw or self._has_card_advantage(oracle_lower)
        tags.ramp = self._has_ramp(oracle_lower, type_lower)
        tags.mana_ritual = self._has_ritual(oracle_lower)
        
        # Interaction
        tags.counterspell = self._has_counterspell(oracle_lower)
        tags.discard = self._has_discard(oracle_lower)
        tags.mill = self._has_mill(oracle_lower)
        
        # Tutors
        tutor_result = self._has_tutor(oracle_lower)
        tags.tutor = tutor_result["any"]
        tags.tutor_creature = tutor_result["creature"]
        tags.tutor_instant_sorcery = tutor_result["instant_sorcery"]
        tags.tutor_artifact = tutor_result["artifact"]
        tags.tutor_enchantment = tutor_result["enchantment"]
        tags.tutor_land = tutor_result["land"]
        
        # Board control
        tags.board_wipe = self._has_board_wipe(oracle_lower)
        tags.stax = self._has_stax(oracle_lower, card_name)
        
        # Graveyard
        tags.recursion = self._has_recursion(oracle_lower)
        tags.reanimation = self._has_reanimation(oracle_lower)
        tags.graveyard_hate = self._has_graveyard_hate(oracle_lower)
        
        # Protection
        tags.hexproof = "hexproof" in oracle_lower or "hexproof" in type_lower
        tags.indestructible = "indestructible" in oracle_lower
        tags.ward = "ward" in oracle_lower
        tags.protection = tags.hexproof or tags.indestructible or tags.ward or ("protection from" in oracle_lower)
        
        # Combat/Evasion
        tags.flying = "flying" in oracle_lower
        tags.menace = "menace" in oracle_lower
        tags.unblockable = "unblockable" in oracle_lower or "can't be blocked" in oracle_lower
        tags.evasion = tags.flying or tags.menace or tags.unblockable or ("evasion" in oracle_lower)
        
        # Win conditions
        tags.alt_win_con = self._has_alt_win_con(oracle_lower)
        tags.combo_piece = self._is_combo_piece(card_name, oracle_lower)
        tags.win_condition = tags.alt_win_con or tags.combo_piece
        
        # Utility
        tags.token_generator = "create" in oracle_lower and "token" in oracle_lower
        tags.life_gain = "gain" in oracle_lower and "life" in oracle_lower
        tags.life_loss = "lose" in oracle_lower and "life" in oracle_lower
        tags.sacrifice_outlet = "sacrifice" in oracle_lower and (":" in oracle_text or "may sacrifice" in oracle_lower)
        
        return tags
    
    def _has_creature_removal(self, oracle: str, type_line: str) -> bool:
        patterns = [
            r"destroy target creature",
            r"exile target creature",
            r"return target creature",
            r"target creature.*\-\d+/\-\d+",
            r"deal \d+ damage to target creature",
            r"deals damage to target creature",
            r"target creature gets \-\d+",
        ]
        
        # Instants/Sorceries that deal damage often are removal
        if ("instant" in type_line or "sorcery" in type_line) and "damage" in oracle:
            if "creature" in oracle or "target" in oracle:
                return True
        
        return any(re.search(p, oracle) for p in patterns)
    
    def _has_artifact_removal(self, oracle: str) -> bool:
        return "destroy target artifact" in oracle or "exile target artifact" in oracle
    
    def _has_enchantment_removal(self, oracle: str) -> bool:
        return "destroy target enchantment" in oracle or "exile target enchantment" in oracle
    
    def _has_planeswalker_removal(self, oracle: str, has_creature_removal: bool) -> bool:
        # Direct planeswalker removal
        if "destroy target planeswalker" in oracle or "exile target planeswalker" in oracle:
            return True
        # Damage to any target / player or planeswalker
        if "any target" in oracle and "damage" in oracle:
            return True
        if "planeswalker" in oracle and "damage" in oracle:
            return True
        # Many creature removal spells can also hit planeswalkers
        if has_creature_removal and "or planeswalker" in oracle:
            return True
        return False
    
    def _has_land_removal(self, oracle: str) -> bool:
        return "destroy target land" in oracle or "exile target land" in oracle or ("target land" in oracle and "sacrifice" in oracle)
    
    def _has_any_permanent_removal(self, oracle: str) -> bool:
        return "destroy target permanent" in oracle or "exile target permanent" in oracle or "destroy target nonland" in oracle
    
    def _has_card_draw(self, oracle: str) -> bool:
        patterns = [
            r"draw (?:a|one|two|three|\d+) cards?",
            r"draws? (?:a|one|two|three|\d+) cards?",
        ]
        return any(re.search(p, oracle) for p in patterns)
    
    def _has_card_advantage(self, oracle: str) -> bool:
        # Broader than draw
        patterns = [
            "draw",
            "exile.*you may cast",
            "exile.*play.*card",
            "look at the top",
            "reveal.*put.*hand",
        ]
        return any(p in oracle for p in patterns)
    
    def _has_ramp(self, oracle: str, type_line: str) -> bool:
        # Permanent mana acceleration
        patterns = [
            "search your library for.*land",
            "add.*mana",
            "adds.*mana",
            "tap.*add.*mana",
        ]
        
        # Exclude one-time rituals
        if "instant" in type_line or "sorcery" in type_line:
            if "search" not in oracle:  # Cultivate-style ramp is OK
                return False
        
        return any(p in oracle for p in patterns)
    
    def _has_ritual(self, oracle: str) -> bool:
        # One-time mana boost (typically instants/sorceries)
        return "add" in oracle and "mana" in oracle and ("instant" in oracle or "sorcery" in oracle)
    
    def _has_counterspell(self, oracle: str) -> bool:
        return "counter target spell" in oracle or "counter target" in oracle
    
    def _has_discard(self, oracle: str) -> bool:
        patterns = [
            "target.*discard",
            "each opponent discards",
            "discard.*card",
        ]
        # Exclude self-discard costs
        if re.search(r"discard.*:", oracle):
            return False
        return any(p in oracle for p in patterns)
    
    def _has_mill(self, oracle: str) -> bool:
        patterns = [
            r"target player mills",
            r"put.*top.*library.*graveyard",
            r"mills? \d+ cards?",
        ]
        return any(re.search(p, oracle) for p in patterns)
    
    def _has_tutor(self, oracle: str) -> Dict[str, bool]:
        result = {"any": False, "creature": False, "instant_sorcery": False, "artifact": False, "enchantment": False, "land": False}
        
        if "search your library" not in oracle:
            return result
        
        result["any"] = True
        
        if "creature" in oracle:
            result["creature"] = True
        if "instant" in oracle or "sorcery" in oracle:
            result["instant_sorcery"] = True
        if "artifact" in oracle:
            result["artifact"] = True
        if "enchantment" in oracle:
            result["enchantment"] = True
        if "land" in oracle:
            result["land"] = True
        
        return result
    
    def _has_board_wipe(self, oracle: str) -> bool:
        # String patterns for simple matching
        simple_patterns = [
            "destroy all creatures",
            "exile all creatures",
            "destroy all permanents",
            "exile all permanents",
        ]
        if any(p in oracle for p in simple_patterns):
            return True
        
        # Regex patterns for complex matching
        regex_patterns = [
            r"-\d+/-\d+ to all creatures",
        ]
        return any(re.search(p, oracle) for p in regex_patterns)
    
    def _has_stax(self, oracle: str, card_name: str) -> bool:
        # Resource denial / taxing effects
        known_stax = ["Thalia", "Winter Orb", "Static Orb", "Smokestack", "Tangle Wire", "Sphere of Resistance"]
        if any(name in card_name for name in known_stax):
            return True
        
        patterns = [
            "spells cost.*more",
            "abilities cost.*more",
            "don't untap",
            "players can't",
            "opponents can't",
        ]
        return any(p in oracle for p in patterns)
    
    def _has_recursion(self, oracle: str) -> bool:
        patterns = [
            "return.*card.*from your graveyard.*hand",
            "return.*card.*from.*graveyard.*battlefield",
            "return target.*card from a graveyard",
        ]
        return any(re.search(p, oracle) for p in patterns)
    
    def _has_reanimation(self, oracle: str) -> bool:
        # Specifically returning creatures from graveyard to battlefield
        return "creature" in oracle and "graveyard" in oracle and "battlefield" in oracle
    
    def _has_graveyard_hate(self, oracle: str) -> bool:
        patterns = [
            "exile.*graveyard",
            "exile all cards from.*graveyard",
            "cards in graveyards can't",
            "graveyards.*can't be",
        ]
        return any(re.search(p, oracle) for p in patterns)
    
    def _has_alt_win_con(self, oracle: str) -> bool:
        return "you win the game" in oracle or "wins the game" in oracle
    
    def _is_combo_piece(self, card_name: str, oracle: str) -> bool:
        # Known combo pieces (this should be expanded)
        known_combos = [
            "Thassa's Oracle", "Demonic Consultation", "Tainted Pact",
            "Kiki-Jiki", "Splinter Twin", "Pestermite", "Deceiver Exarch",
            "Underworld Breach", "Brain Freeze", "LED",
            "Doomsday", "Grindstone", "Painter's Servant",
        ]
        
        # Heuristic: infinite combos often have "untap" or "copy" or "exile your library"
        if any(name in card_name for name in known_combos):
            return True
        
        patterns = [
            "infinite",
            "untap.*permanent",
            "copy.*spell",
            "exile your library",
        ]
        return any(p in oracle for p in patterns)
    
    def tag_deck_cards(self, deck_cards: List[str]) -> Dict[str, FunctionalTags]:
        """Tag all cards in a deck"""
        result = {}
        for card_name in deck_cards:
            result[card_name] = self.tag_card(card_name)
        return result
    
    def export_tags(self, output_path: Path):
        """Export all tags for cards in database"""
        print(f"Tagging {len(self.card_db)} cards...")
        
        results = []
        for card_name in self.card_db:
            tags = self.tag_card(card_name)
            results.append(asdict(tags))
        
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        print(f"✅ Exported {len(results)} card tags to {output_path}")
    
    def analyze_tags(self, tags_list: List[FunctionalTags]):
        """Analyze tag distribution"""
        stats = {}
        total = len(tags_list)
        
        for tag_name in FunctionalTags.__dataclass_fields__.keys():
            if tag_name == "card_name":
                continue
            count = sum(1 for tags in tags_list if getattr(tags, tag_name))
            if count > 0:
                stats[tag_name] = (count, f"{100*count/total:.1f}%")
        
        # Sort by frequency
        for tag, (count, pct) in sorted(stats.items(), key=lambda x: -x[1][0]):
            print(f"{tag:30s}: {count:5d} ({pct})")


if __name__ == "__main__":
    tagger = FunctionalTagger()
    
    # Export all tags
    output = Path("card_functional_tags.json")
    tagger.export_tags(output)
    
    # Show statistics
    print("\n📊 Tag Distribution:")
    with open(output) as f:
        all_tags = [FunctionalTags(**item) for item in json.load(f)]
    tagger.analyze_tags(all_tags)
