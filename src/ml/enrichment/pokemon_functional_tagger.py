#!/usr/bin/env python3
"""
Pokemon Functional Tagging System

Assigns functional roles/tags to Pokemon cards based on their attacks, abilities, and characteristics.

Functional roles:
- Attackers (damage dealers)
- Energy acceleration (ramp)
- Card draw / search
- Disruption (hand/bench/energy)
- Tanking/walls
- Evolution support
- Setup (Abilities that set up board state)
- Tech cards (counters, hate cards)
"""

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List


@dataclass
class PokemonFunctionalTags:
    """Functional classification for a Pokemon card"""
    card_name: str
    card_type: str  # Pokemon, Trainer, Energy
    
    # Pokemon-specific (for Pokemon cards)
    heavy_hitter: bool = False  # 100+ damage per turn
    spread_attacker: bool = False  # Damages multiple targets
    sniper: bool = False  # Damages bench directly
    tank: bool = False  # 200+ HP
    wall: bool = False  # Forces opponent to switch or stall
    
    # Energy/Acceleration
    energy_acceleration: bool = False  # Attaches extra energy
    energy_recovery: bool = False  # Recovers energy from discard
    energy_disruption: bool = False  # Discards opponent's energy
    
    # Draw/Search
    draw_support: bool = False  # Draws cards
    search_pokemon: bool = False  # Searches for Pokemon
    search_trainer: bool = False  # Searches for Trainers
    search_energy: bool = False  # Searches for Energy
    search_any: bool = False  # Generic search
    
    # Disruption
    hand_disruption: bool = False  # Disrupts opponent's hand
    bench_disruption: bool = False  # Forces bench Pokemon out
    ability_lock: bool = False  # Locks Abilities
    item_lock: bool = False  # Locks Item cards
    supporter_lock: bool = False  # Locks Supporter cards
    
    # Healing/Protection
    healing: bool = False  # Heals damage
    damage_reduction: bool = False  # Reduces incoming damage
    protection: bool = False  # Prevents effects
    
    # Setup/Support
    evolution_support: bool = False  # Helps evolve Pokemon
    setup_ability: bool = False  # Ability that sets up plays
    pivot: bool = False  # Free retreat or switching support
    
    # Special mechanics
    gx_attack: bool = False  # Has GX attack
    v_star_power: bool = False  # Has VSTAR Power
    vmax: bool = False  # Is a VMAX Pokemon
    rule_box: bool = False  # Has a rule box (GX, V, VSTAR, etc.)
    
    # Tech/Hate
    special_energy_hate: bool = False
    tool_hate: bool = False
    stadium_hate: bool = False
    evolution_hate: bool = False


class PokemonFunctionalTagger:
    """Tags Pokemon cards with functional roles"""
    
    def tag_card(self, card_data: dict) -> PokemonFunctionalTags:
        """Tag a Pokemon card with functional roles"""
        name = card_data.get("name", "")
        supertype = card_data.get("supertype", "")
        subtypes = card_data.get("subtypes", [])
        hp = card_data.get("hp", "")
        attacks = card_data.get("attacks", [])
        abilities = card_data.get("abilities", [])
        rules = card_data.get("rules", [])
        
        tags = PokemonFunctionalTags(
            card_name=name,
            card_type=supertype
        )
        
        # Pokemon-specific tags
        if supertype == "Pokémon":
            tags = self._tag_pokemon(tags, hp, attacks, abilities, subtypes, rules)
        
        # Trainer-specific tags
        elif supertype == "Trainer":
            tags = self._tag_trainer(tags, card_data, subtypes)
        
        return tags
    
    def _tag_pokemon(self, tags, hp, attacks, abilities, subtypes, rules):
        """Tag Pokemon cards"""
        
        # HP-based
        try:
            hp_val = int(hp) if hp else 0
            if hp_val >= 200:
                tags.tank = True
        except:
            pass
        
        # Rule box (GX, V, VSTAR, VMAX, etc.)
        if rules:
            tags.rule_box = True
            for rule in rules:
                if "GX" in rule:
                    tags.gx_attack = True
                if "VSTAR" in rule:
                    tags.v_star_power = True
        
        if "VMAX" in subtypes:
            tags.vmax = True
        
        # Analyze attacks
        for attack in attacks:
            attack_name = attack.get("name", "").lower()
            attack_text = attack.get("text", "").lower()
            damage = attack.get("damage", "")
            
            # Damage classification
            try:
                if damage and damage != "":
                    dmg_val = int(damage.replace("+", "").replace("×", ""))
                    if dmg_val >= 100:
                        tags.heavy_hitter = True
            except:
                pass
            
            # Spread/Snipe
            if "each of your opponent" in attack_text or "to each" in attack_text:
                tags.spread_attacker = True
            if "benched pokémon" in attack_text or "bench" in attack_text:
                tags.sniper = True
            
            # Disruption
            if "discard" in attack_text and "energy" in attack_text:
                tags.energy_disruption = True
            if "hand" in attack_text and ("discard" in attack_text or "shuffle" in attack_text):
                tags.hand_disruption = True
            if "switch" in attack_text and "opponent" in attack_text:
                tags.bench_disruption = True
        
        # Analyze abilities
        for ability in abilities:
            ability_name = ability.get("name", "").lower()
            ability_text = ability.get("text", "").lower()
            
            # Energy acceleration
            if "attach" in ability_text and "energy" in ability_text:
                tags.energy_acceleration = True
            if "energy" in ability_text and ("from your discard" in ability_text or "discard pile" in ability_text):
                tags.energy_recovery = True
            
            # Draw/Search
            if "draw" in ability_text and "card" in ability_text:
                tags.draw_support = True
            if "search your deck" in ability_text:
                tags.search_any = True
                if "pokémon" in ability_text:
                    tags.search_pokemon = True
                if "energy" in ability_text:
                    tags.search_energy = True
                if "trainer" in ability_text or "item" in ability_text:
                    tags.search_trainer = True
            
            # Locks
            if ("can't use" in ability_text or "cannot use" in ability_text) and "abilities" in ability_text:
                tags.ability_lock = True
            if ("can't play" in ability_text or "cannot play" in ability_text) and "item" in ability_text:
                tags.item_lock = True
            if ("can't play" in ability_text or "cannot play" in ability_text) and "supporter" in ability_text:
                tags.supporter_lock = True
            
            # Healing
            if "heal" in ability_text:
                tags.healing = True
            if "prevent" in ability_text and "damage" in ability_text:
                tags.damage_reduction = True
            
            # Setup
            if "evolve" in ability_text:
                tags.evolution_support = True
            if ability_text and ("once during your turn" in ability_text or "when you play" in ability_text):
                tags.setup_ability = True
            
            # Wall effects
            if "can't attack" in ability_text or "must" in ability_text:
                tags.wall = True
        
        return tags
    
    def _tag_trainer(self, tags, card_data, subtypes):
        """Tag Trainer cards"""
        
        # Pokemon TCG API provides effect text in 'rules' field for Trainers
        text_sources = []
        if "text" in card_data:
            text_sources.append(card_data.get("text", ""))
        if "rules" in card_data:
            rules = card_data.get("rules", [])
            if isinstance(rules, list):
                text_sources.extend(rules)
            else:
                text_sources.append(str(rules))
        
        text = " ".join(text_sources).lower()
        
        # Search cards
        if "search your deck" in text:
            tags.search_any = True
            if "pokémon" in text:
                tags.search_pokemon = True
            if "energy" in text:
                tags.search_energy = True
            if "trainer" in text or "item" in text or "supporter" in text:
                tags.search_trainer = True
        
        # Draw cards
        if "draw" in text and "card" in text:
            tags.draw_support = True
        
        # Energy acceleration
        if "attach" in text and "energy" in text:
            tags.energy_acceleration = True
        if "energy" in text and ("from your discard" in text or "discard pile" in text):
            tags.energy_recovery = True
        
        # Disruption
        if "discard" in text and ("opponent" in text or "defending pokémon" in text) and "energy" in text:
            tags.energy_disruption = True
        if "hand" in text and ("discard" in text or "shuffle" in text) and "opponent" in text:
            tags.hand_disruption = True
        
        # Healing
        if "heal" in text:
            tags.healing = True
        
        # Switching
        if "switch" in text or "retreat" in text:
            tags.pivot = True
        
        # Hate cards
        if "discard" in text and "special energy" in text:
            tags.special_energy_hate = True
        if "discard" in text and "tool" in text:
            tags.tool_hate = True
        if "discard" in text and "stadium" in text:
            tags.stadium_hate = True
        
        return tags
    
    def tag_deck_cards(self, deck_cards: List[dict]) -> Dict[str, PokemonFunctionalTags]:
        """Tag all cards in a deck"""
        result = {}
        for card_data in deck_cards:
            name = card_data.get("name", "")
            if name:
                result[name] = self.tag_card(card_data)
        return result
    
    def export_tags(self, cards_data: List[dict], output_path: Path):
        """Export all tags for Pokemon cards"""
        print(f"Tagging {len(cards_data)} Pokemon cards...")
        
        results = []
        for card_data in cards_data:
            tags = self.tag_card(card_data)
            results.append(asdict(tags))
        
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        print(f"✅ Exported {len(results)} Pokemon card tags to {output_path}")


if __name__ == "__main__":
    # Example usage - would load from actual Pokemon card database
    tagger = PokemonFunctionalTagger()
    
    # Example card
    example_card = {
        "name": "Charizard ex",
        "supertype": "Pokémon",
        "subtypes": ["Basic", "ex"],
        "hp": "220",
        "attacks": [
            {
                "name": "Burning Darkness",
                "cost": ["Fire", "Fire", "Colorless"],
                "damage": "180",
                "text": "Discard 2 Energy from this Pokémon."
            }
        ],
        "abilities": [
            {
                "name": "Infernal Reign",
                "text": "Once during your turn, you may search your deck for up to 3 basic Fire Energy cards and attach them to your Pokémon in any way you like. Then, shuffle your deck.",
                "type": "Ability"
            }
        ],
        "rules": ["Pokémon ex rule: When your Pokémon ex is Knocked Out, your opponent takes 2 Prize cards."]
    }
    
    tags = tagger.tag_card(example_card)
    print(f"\n{tags.card_name} tags:")
    print(f"  Heavy Hitter: {tags.heavy_hitter}")
    print(f"  Energy Acceleration: {tags.energy_acceleration}")
    print(f"  Rule Box: {tags.rule_box}")
    print(f"  Tank: {tags.tank}")
