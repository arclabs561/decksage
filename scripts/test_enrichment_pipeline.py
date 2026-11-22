#!/usr/bin/env python3
"""Offline smoke checks for card pricing and the two rule-based functional taggers."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ml.enrichment.card_market_data import MarketDataManager
from ml.enrichment.pokemon_functional_tagger import PokemonFunctionalTagger
from ml.enrichment.yugioh_functional_tagger import YugiohFunctionalTagger


def check_market_data():
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name, usd in [("Bolt", "1.25"), ("Free", "0.00"), ("Unknown", None)]:
            (directory / f"{name}.json").write_text(
                json.dumps({"name": name, "prices": {"usd": usd}})
            )
        manager = MarketDataManager(directory)
        result = manager.get_deck_price({"Bolt": 4, "Free": 2, "Unknown": 1})
        if (result["total_usd"], result["coverage"], result["missing_prices"]) != (
            5.0,
            "2/3",
            ["Unknown"],
        ):
            raise AssertionError(f"Incorrect deck price or coverage: {result}")


def check_pokemon():
    sample_card = {
        "name": "Charizard ex",
        "supertype": "Pokémon",
        "subtypes": ["Basic", "ex"],
        "hp": "220",
        "attacks": [
            {
                "name": "Burning Darkness",
                "damage": "180",
                "cost": ["Fire", "Fire", "Colorless"],
                "text": "Discard 2 Energy from this Pokémon.",
            }
        ],
        "abilities": [
            {
                "name": "Infernal Reign",
                "text": "Once during your turn, you may search your deck for up to 3 basic Fire Energy cards and attach them to your Pokémon in any way you like.",
                "type": "Ability",
            }
        ],
    }
    tags = PokemonFunctionalTagger().tag_card(sample_card)
    if not (tags.heavy_hitter and tags.energy_acceleration and tags.tank):
        raise AssertionError(f"Missing Charizard tags: {tags}")


def check_yugioh():
    sample_card = {
        "name": "Ash Blossom & Joyous Spring",
        "type": "Effect Monster",
        "desc": "When a card or effect is activated that includes any of these effects (Quick Effect): You can discard this card; negate that effect. ● Add a card from the Deck to the hand. ● Special Summon from the Deck. ● Send a card from the Deck to the GY.",
    }
    tags = YugiohFunctionalTagger().tag_card(sample_card)
    if not (tags.hand_trap and tags.effect_negation and tags.quick_effect):
        raise AssertionError(f"Missing Ash Blossom tags: {tags}")


if __name__ == "__main__":
    for check, label in [
        (check_market_data, "Scryfall fixture pricing"),
        (check_pokemon, "Pokémon functional tags"),
        (check_yugioh, "Yu-Gi-Oh! functional tags"),
    ]:
        check()
        print(f"Passed: {label}")
