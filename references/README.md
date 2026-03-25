# References

Design and style anchors for DeckSage UI/UX. Each game's official rulebook provides the canonical visual language to model per-game theme overlays.

## Rulebooks

| Game | File | Source | Pages |
|------|------|--------|-------|
| Yu-Gi-Oh | `rulebooks/yugioh_rulebook.pdf` | [Konami official](https://img.yugioh-card.com/en/downloads/rulebook/SD_RuleBook_EN_10.pdf) | ~50 |
| Magic (Comp Rules) | `rulebooks/magic_comp_rules_2026.pdf` | [Wizards 2026-02-27](https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.pdf) | Dense text; terminology/mechanics reference |
| Magic (Basic) | `rulebooks/magic_basic_rulebook.pdf` | [officialgamerules.org](https://officialgamerules.org/wp-content/uploads/2025/02/Magic-The-Gathering-Rulebook.pdf) | 20 |
| Pokemon | `rulebooks/pokemon_quick_start.pdf` | [pokemon.com](https://tcg.pokemon.com/assets/img/learn-to-play/getting-started/quick-start-rules/en-us/quick_start_rulebook.pdf) | 19 |

## Pull

```bash
./references/pull_references.sh
```

Downloads all PDFs. Pokemon may need full browser headers (Cloudflare). The script handles this automatically. The entire `references/` directory is gitignored except this README and the pull script.

---

## Visual Design Language Analysis

Extracted from visual inspection of rulebook pages. Use these as anchors for per-game theme overlays in the frontend.

### Yu-Gi-Oh

**Overall feel**: Angular, high-energy, dramatic. Targets younger audience with bold visual impact.

**Color palette**:
- Primary: Deep magenta/fuchsia (`#C2185B` range) for headers and section markers
- Secondary: Gold/bronze (`#C9A54E`) for ornamental borders and accents
- Background: Warm parchment/aged paper texture with radial gold gradient patterns
- Card frame: Purple geometric diamond lattice pattern for page backgrounds
- Section tabs: Color-coded by chapter -- orange (Getting Started), green (Game Cards), blue (How to Play), pink (Battles), purple (Other Rules)
- Attribute icons: Circular, each a distinct saturated color (DARK purple, FIRE red, EARTH brown, WATER blue, WIND green, LIGHT yellow)

**Typography**:
- Headings: Bold uppercase sans-serif, heavy weight, often with decorative banners/ribbons behind them
- Section titles in ornamental boxes with rounded corners and colored fills (red "Example" boxes, blue "HOW TO READ A CARD" banners)
- Body: Clean sans-serif, moderate size, well-spaced
- The Yu-Gi-Oh! logo itself uses a distinctive angular stylized font with exclamation mark

**Layout patterns**:
- Two-column spread (left page + right page as a unit)
- Heavy use of annotated card images with numbered callout labels (1-9 for card anatomy)
- Side tabs on page edges for chapter navigation (colored vertical strips)
- Generous card image sizing -- cards shown at near-actual proportions
- Callout boxes with colored backgrounds for definitions, examples, tips
- Decorative borders around content regions

**Iconography**:
- Attribute icons: circular with kanji-inspired symbols (DARK, LIGHT, FIRE, WATER, EARTH, WIND)
- Level stars: orange/yellow star icons
- Card type indicators use color + icon (Spell = green, Trap = magenta)
- Numbered step indicators in colored circles

**Key UI/UX anchors for DeckSage**:
- Use the magenta/gold/parchment palette for Yu-Gi-Oh theme
- Annotated card callouts for card detail views
- Color-coded section tabs for navigation
- Angular, energetic geometry for decorative elements
- Side-tab navigation pattern for multi-section views

---

### Magic: The Gathering

**Overall feel**: Dark, atmospheric, painterly. Fantasy illustration-driven. More mature/sophisticated than Yu-Gi-Oh or Pokemon.

**Color palette**:
- Primary: Deep navy/dark blue-grey (`#1B2838` range) for backgrounds, headers, borders
- Secondary: Warm copper/rust/bronze (`#8B4513` to `#CD7F32`) for metallic accents
- Text: Near-black on white/cream body, white on dark headers
- The five mana colors are the defining chromatic system:
  - White: bright warm white/cream
  - Blue: ocean blue (`#0E68AB`)
  - Black: deep charcoal/violet-black
  - Red: volcanic red-orange (`#D32F2F`)
  - Green: forest green (`#2E7D32`)
- Section headers: dark blue gradient banner with distressed/textured edges (like worn parchment or cracked stone)
- Page footer: dark semicircular banner with section name in small caps

**Typography**:
- Headings: Beleren (Magic's signature font) -- a distinctive small-caps serif with wide tracking. Used for section titles, card type names. Very recognizable.
- "CONTENTS", "THE BASICS", "PARTS OF A CARD" all in this distinctive small-caps serif
- Subheadings: bold serif, title case
- Body: Clean serif (likely Garamond or similar), well-leaded, comfortable reading size
- Card names in bold when referenced in text
- Italics used for game terms on first introduction (e.g., *mana*, *tapping*, *permanent*)

**Layout patterns**:
- Single-column with generous margins (book-like)
- Card images inset into text flow, left-aligned or right-aligned, text wraps around
- Card anatomy shown with labeled arrows pointing to card regions (Card Name, Mana Cost, Type Line, Text Box, Power/Toughness, etc.)
- Clean section dividers: dark horizontal banner with section title centered
- Page numbers in small dark semicircle at bottom center
- The mana wheel (5-color pentagon) is a central organizing visual
- White space is generous -- not cramped
- Bordered content boxes for table of contents

**Iconography**:
- Mana symbols: circular with distinct interior symbol per color (sun, water drop, skull, flame, tree)
- Tap symbol (curved arrow)
- Expansion set symbols (rarity indicated by color: black/common, silver/uncommon, gold/rare, orange-red/mythic)
- Card type has no icon -- conveyed through type line text and card frame color

**Key UI/UX anchors for DeckSage**:
- Dark blue/bronze palette with the 5-color mana system as accent colors
- Beleren-inspired heading typography (or a similar distinctive small-caps serif)
- Painterly, atmospheric feel -- dark backgrounds with warm highlights
- Card images with labeled anatomy arrows for detail views
- Single-column, book-like layouts with generous whitespace
- The mana wheel as a navigational/organizational element for color-based filtering

---

### Pokemon TCG

**Overall feel**: Bright, playful, approachable. Highest production value of the three. Targets all ages with clear visual hierarchy and friendly character art.

**Color palette**:
- Primary: Grass green (`#2E7D32` to `#4CAF50`) for borders, headers, and structural elements
- The Poke Ball motif (red top / white bottom) appears as page number indicators
- Section headers: dark green bar with white text
- Step indicators: vibrant rainbow progression -- each numbered step gets its own saturated color:
  - 1: Red/crimson (`#E53935`)
  - 2: Blue (`#1E88E5`)
  - 3: Green (`#43A047`)
  - 4: Teal (`#00897B`)
  - 5: Purple (`#8E24AA`)
  - 6: Magenta/pink (`#D81B60`)
  - 7: Orange-red for attack step
- Game mat zones: distinct colors -- purple/blue for opponent's area, red/pink for bench, grey for deck
- Callout boxes: red headers with white text ("Trainer Tip!" in Poke Ball icon), green/red for success/failure indicators
- Check/X indicators: green checkmark, red X for valid/invalid plays

**Typography**:
- Headings: Bold sans-serif, dark on light backgrounds, white on dark bars
- Step labels: bold sans-serif in colored arrow/chevron shapes (pointing right)
- Body: Clean sans-serif, larger than Magic or Yu-Gi-Oh (accessibility-oriented)
- "Trainer Tip!" callouts in distinct style
- Card names and game terms in bold
- Page numbers inside Poke Ball-styled circles at bottom corners

**Layout patterns**:
- Two-column spread (like Yu-Gi-Oh), but with more illustration and less text density
- Game state diagrams: full board layout shown (bench, active, discard, deck) with colored zones and arrows showing card movement
- Arrow annotations (red, blue) showing where cards move during play steps
- Numbered step sequences with colored chevrons as step indicators
- Large character illustrations (Pikachu, Eevee, etc.) used as visual anchors alongside content
- Card anatomy shown similarly to others: labeled arrows to card regions
- High illustration-to-text ratio -- very visual teaching approach
- Callout boxes for tips with Poke Ball icon

**Iconography**:
- Energy type symbols: circular, each a distinct color/shape (Grass leaf, Fire flame, Water droplet, Lightning bolt, Psychic eye, Fighting fist, Dark crescent, Metal hexagon, Fairy star, Dragon claw, Colorless star)
- Poke Ball as a universal motif (page numbers, tip callouts, general branding)
- Evolution arrows (showing Basic -> Stage 1 -> Stage 2)
- Weakness/resistance arrows with type symbols
- Retreat cost shown as colorless energy symbols in a row

**Key UI/UX anchors for DeckSage**:
- Green-dominant palette with rainbow step indicators
- Poke Ball motif for branding elements and indicators
- Bright, high-contrast, accessibility-first color choices
- Game board diagrams for deck completion/suggestion visualizations
- Energy type symbols as the primary iconographic system (equivalent to mana symbols)
- Large friendly character art as visual anchors
- Colored chevron/arrow step indicators for multi-step flows
- Green/red success/failure indicators

---

## Cross-Game Comparison

| Aspect | Yu-Gi-Oh | Magic | Pokemon |
|--------|----------|-------|---------|
| Mood | Angular, dramatic, energetic | Dark, atmospheric, painterly | Bright, playful, approachable |
| Primary color | Magenta + gold | Navy + bronze | Green + rainbow |
| Background | Parchment texture, geometric | White/cream, book-like | White, clean |
| Heading style | Bold sans uppercase in colored banners | Small-caps serif (Beleren) | Bold sans in dark bars |
| Body text | Sans-serif | Serif (Garamond-like) | Sans-serif (large) |
| Card anatomy | Numbered callouts (1-9) | Labeled arrows | Labeled arrows |
| Navigation | Color-coded side tabs | Section banners with page footers | Colored chevron steps |
| Core icon system | Attribute circles (6) | Mana symbols (5 colors) | Energy types (11) |
| Information density | Medium | High | Low (visual-first) |
| Page layout | 2-column spread | Single column | 2-column spread |

## Application to DeckSage Themes

The frontend already has an Encarta base theme with game overlays. These rulebooks provide the authoritative source for:

1. **Per-game color tokens**: extract exact hex values from card frames and rulebook headers for CSS custom properties
2. **Typography choices**: Beleren-style for Magic, bold angular sans for Yu-Gi-Oh, friendly rounded sans for Pokemon
3. **Card detail views**: follow each game's card anatomy diagram pattern for the card info panel
4. **Icon systems**: mana symbols (Magic), attribute icons (Yu-Gi-Oh), energy types (Pokemon) for type filters and card annotations
5. **Layout density**: dense single-column for Magic users, visual two-column for Pokemon/Yu-Gi-Oh
6. **Callout patterns**: red/gold ornamental boxes (Yu-Gi-Oh), dark banners (Magic), colored tips with Poke Ball (Pokemon)
