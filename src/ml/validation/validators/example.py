#!/usr/bin/env python3
"""
Example usage of data validators.

Demonstrates:
1. Creating validated decks
2. Handling validation errors
3. Loading data from files
4. Checking ban lists
"""

from pydantic import ValidationError

from .models import CardDesc, MTGDeck, Partition, PokemonDeck, YugiohDeck


def example_valid_decks():
    """Create valid decks for each game."""
    print("=" * 60)
    print("EXAMPLE 1: Valid Decks")
    print("=" * 60)

    # MTG Modern Burn
    mtg_deck = MTGDeck(
        deck_id="modern_burn",
        format="Modern",
        archetype="Burn",
        partitions=[
            Partition(
                name="Main",
                cards=[
                    CardDesc(name="Lightning Bolt", count=4),
                    CardDesc(name="Lava Spike", count=4),
                    CardDesc(name="Rift Bolt", count=4),
                    CardDesc(name="Monastery Swiftspear", count=4),
                    CardDesc(name="Goblin Guide", count=4),
                    CardDesc(name="Eidolon of the Great Revel", count=4),
                    CardDesc(name="Searing Blaze", count=4),
                    CardDesc(name="Skullcrack", count=4),
                    CardDesc(name="Boros Charm", count=4),
                    CardDesc(name="Inspiring Vantage", count=4),
                    CardDesc(name="Sacred Foundry", count=4),
                    CardDesc(name="Sunbaked Canyon", count=4),
                    CardDesc(name="Mountain", count=12),
                ],
            ),
            Partition(
                name="Sideboard",
                cards=[
                    CardDesc(name="Path to Exile", count=3),
                    CardDesc(name="Rest in Peace", count=3),
                    CardDesc(name="Wear // Tear", count=3),
                    CardDesc(name="Deflecting Palm", count=3),
                    CardDesc(name="Smash to Smithereens", count=3),
                ],
            ),
        ],
    )
    print(f"✓ MTG {mtg_deck.format} {mtg_deck.archetype}")
    print(f"  Main: {mtg_deck.get_main_deck().total_cards()} cards")
    print(f"  Sideboard: {mtg_deck.get_sideboard().total_cards()} cards")

    # Yu-Gi-Oh! Blue-Eyes
    ygo_deck = YugiohDeck(
        deck_id="blue_eyes",
        format="TCG",
        archetype="Blue-Eyes",
        partitions=[
            Partition(
                name="Main Deck",
                cards=[
                    CardDesc(name="Blue-Eyes White Dragon", count=3),
                    CardDesc(name="Blue-Eyes Alternative White Dragon", count=3),
                    CardDesc(name="The White Stone of Ancients", count=3),
                    CardDesc(name="Sage with Eyes of Blue", count=3),
                ]
                + [CardDesc(name=f"Support Card {i}", count=1) for i in range(28)],
            ),
            Partition(
                name="Extra Deck",
                cards=[
                    CardDesc(name="Blue-Eyes Ultimate Dragon", count=1),
                    CardDesc(name="Blue-Eyes Twin Burst Dragon", count=2),
                ],
            ),
        ],
    )
    print(f"\n✓ YGO {ygo_deck.archetype}")
    print(f"  Main: {ygo_deck.partitions[0].total_cards()} cards")
    print(f"  Extra: {ygo_deck.partitions[1].total_cards()} cards")

    # Pokemon Pikachu deck
    pkmn_deck = PokemonDeck(
        deck_id="pikarom",
        format="Standard",
        archetype="Pikarom",
        partitions=[
            Partition(
                name="Main Deck",
                cards=[
                    CardDesc(name="Pikachu & Zekrom-GX", count=4),
                    CardDesc(name="Tapu Koko Prism Star", count=1),
                    CardDesc(name="Zeraora-GX", count=2),
                    CardDesc(name="Lightning Energy", count=13),
                    CardDesc(name="Professor's Research", count=4),
                    CardDesc(name="Boss's Orders", count=4),
                    CardDesc(name="Marnie", count=3),
                    CardDesc(name="Quick Ball", count=4),
                    CardDesc(name="Evolution Incense", count=4),
                    CardDesc(name="Switch", count=3),
                ]
                + [CardDesc(name=f"Trainer {i}", count=1) for i in range(18)],
            ),
        ],
    )
    print(f"\n✓ Pokemon {pkmn_deck.archetype}")
    print(f"  Main: {pkmn_deck.partitions[0].total_cards()} cards")


def example_validation_errors():
    """Demonstrate validation errors."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Validation Errors")
    print("=" * 60)

    # Error 1: Too many copies
    print("\nError 1: Too many copies (4-of rule)")
    try:
        MTGDeck(
            deck_id="bad_copies",
            format="Modern",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=5),  # Illegal!
                        CardDesc(name="Mountain", count=55),
                    ],
                ),
            ],
        )
    except ValidationError as e:
        print(f"  ✗ {e.errors()[0]['msg']}")

    # Error 2: Deck too small
    print("\nError 2: Deck too small")
    try:
        MTGDeck(
            deck_id="too_small",
            format="Modern",
            partitions=[
                Partition(
                    name="Main",
                    cards=[CardDesc(name="Lightning Bolt", count=4)],
                ),
            ],
        )
    except ValidationError as e:
        print(f"  ✗ {e.errors()[0]['msg']}")

    # Error 3: Commander not singleton
    print("\nError 3: Commander must be singleton")
    try:
        MTGDeck(
            deck_id="bad_commander",
            format="Commander",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=2),  # Must be 1!
                        CardDesc(name="Mountain", count=98),
                    ],
                ),
            ],
        )
    except ValidationError as e:
        print(f"  ✗ {e.errors()[0]['msg']}")

    # Error 4: Bad card name
    print("\nError 4: Invalid card name (control character)")
    try:
        CardDesc(name="Lightning\x00Bolt", count=4)
    except ValidationError as e:
        print(f"  ✗ {e.errors()[0]['msg']}")


def example_data_loading():
    """Demonstrate loading data from files."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Data Loading")
    print("=" * 60)

    # This is a placeholder - in real usage you'd point to actual data files
    print("\nLenient loading (for ML pipelines):")
    print("```python")
    print("from .loader import load_decks_lenient")
    print("")
    print("decks = load_decks_lenient(")
    print('    Path("decks_hetero.jsonl"),')
    print("    check_legality=False,  # Skip expensive API calls")
    print('    game="auto",           # Auto-detect game type')
    print("    verbose=True,")
    print(")")
    print("")
    print("# Output:")
    print("# Loaded 9847/10000 decks successfully")
    print("#   Parse failures: 23")
    print("#   Schema violations: 130")
    print("#   Legality issues: 0")
    print("```")

    print("\nStrict loading (for critical pipelines):")
    print("```python")
    print("from validators.loader import load_decks_strict")
    print("")
    print("try:")
    print("    decks = load_decks_strict(")
    print('        Path("tournament_data.jsonl"),')
    print("        check_legality=True,  # Enforce ban lists")
    print('        game="magic",')
    print("    )")
    print("except ValidationError as e:")
    print('    print(f"Invalid deck: {e}")')
    print("```")


def example_ban_list_checking():
    """Demonstrate ban list checking."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Ban List Checking")
    print("=" * 60)

    print("\nNote: This requires API calls and caching.")
    print("Run this manually to test:")
    print("")
    print("```python")
    print("from .legality import check_deck_legality")
    print("")
    print("# Check a deck")
    print("issues = check_deck_legality(deck)")
    print("")
    print("if issues:")
    print('    print("Deck has legality issues:")')
    print("    for issue in issues:")
    print('        print(f"  - {issue}")')
    print("    # Example output:")
    print("    #   - Oko, Thief of Crowns is banned in Modern")
    print("    #   - Once Upon a Time is banned in Modern")
    print("else:")
    print('    print("Deck is legal!")')
    print("```")
    print("")
    print("Ban lists are cached in .cache/ban_lists/ (7-day TTL)")


if __name__ == "__main__":
    example_valid_decks()
    example_validation_errors()
    example_data_loading()
    example_ban_list_checking()

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)
    print("\nSee validators/README.md for more details.")
