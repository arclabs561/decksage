# Data Usage and Copyright Information

## What Data Is Stored

This repository stores only **metadata** about trading cards, not copyrighted content:

### Stored (Low Risk)
- **Card names** - Factual data, generally not copyrightable
- **Card types** - Factual classifications (e.g., "Creature", "Instant")
- **Mana costs** - Factual data (e.g., "{R}", "{1}{B}")
- **Colors** - Factual data (e.g., "Red", "Blue")
- **Rarity** - Factual data (e.g., "Common", "Rare")
- **Deck lists** - Public tournament data (card names and counts only)

### NOT Stored (Copyrighted Content)
- ❌ **Card text** (oracle text, flavor text) - Copyrighted by game publishers
- ❌ **Card artwork** - Copyrighted by game publishers/artists
- ❌ **Card images** - Copyrighted by game publishers/artists
- ❌ **Game rules text** - Copyrighted by game publishers

## Data Sources

### Scryfall API
- **Source**: https://scryfall.com/docs/api
- **Data**: Magic: The Gathering card metadata
- **Terms**: Public API, allows data use per their terms of service
- **What we use**: Card names, types, mana costs, colors, rarity
- **What we don't use**: Oracle text, flavor text, images

### Pokemon TCG API
- **Source**: https://pokemontcg.io/
- **Data**: Pokemon Trading Card Game metadata
- **Terms**: Public API, allows data use per their terms of service
- **What we use**: Card names, types, HP, energy costs
- **What we don't use**: Attack text, ability text, images

### Tournament Deck Lists
- **Source**: Public tournament sites (MTGGoldfish, etc.)
- **Data**: Public tournament deck lists
- **What we use**: Card names and counts only
- **What we don't use**: Player names, event details beyond format/archetype

## Backend Code

The backend code (`src/backend/games/*/dataset/*.go`) extracts data from APIs, including
fields for card text. However:

- **Card text fields are extracted but NOT stored** in tracked data files
- Only metadata fields are persisted to disk
- Card text extraction exists for API compatibility but is discarded

## Legal Considerations

### Card Names
Card names are factual data and are generally not subject to copyright protection
under US copyright law (facts cannot be copyrighted).

### Card Text
Card text (oracle text, flavor text) is creative expression and is copyrighted
by game publishers. This project does not store card text.

### Card Artwork
Card artwork is copyrighted by game publishers and/or individual artists.
This project does not store any card artwork or images.

### Game Mechanics
Game mechanics may be protected by patents, but the mechanics themselves are
not stored - only metadata about which cards exist and their factual properties.

### Fair Use
This project is intended for research and educational purposes. The use of factual
metadata (card names, types) for research/analysis purposes may qualify as fair use,
but commercial use may require appropriate licensing.

## Trademarks

- **Magic: The Gathering** is a trademark of Wizards of the Coast LLC
- **Pokemon** is a trademark of Nintendo, Creatures Inc., and Game Freak Inc.
- This project is not affiliated with, endorsed by, or sponsored by these companies

## Questions or Concerns

If you have questions about data usage or copyright concerns, please open an issue
or contact the project maintainers.
