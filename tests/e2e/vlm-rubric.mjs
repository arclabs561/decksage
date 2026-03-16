/**
 * Shared VLM rubric and per-game context for visual quality evaluation.
 *
 * Used by both:
 *   - tests/e2e/visual.spec.mjs   (Playwright CI gate)
 *   - scripts/vlm_critique.mjs    (detailed standalone report)
 *
 * The CARD_GAME_RUBRIC object is passed directly to ai-visual-test's
 * validateWithRubric(), which handles prompt construction and dimension
 * score extraction. No manual prompt serialization needed.
 */

export const PASS_THRESHOLD = 7;

// ---------------------------------------------------------------------------
// 7-dimension rubric tuned for card-game search UIs
// ---------------------------------------------------------------------------

export const CARD_GAME_RUBRIC = {
  score: {
    description: 'Overall visual quality score 0-10',
    criteria: {
      10: 'Perfect -- Apple-level polish with clear game identity through accent color and typography',
      9:  'Excellent -- clean, minimal, game identity unmistakable via accents',
      8:  'Very good -- white/light background, readable, clear information hierarchy',
      7:  'Good -- mostly clean with minor density or contrast issues',
      6:  'Acceptable -- too busy, too much visual noise, or game identity unclear',
      5:  'Needs work -- poor contrast, heavy borders, cramped layout',
      4:  'Poor -- broken layout, illegible text, cluttered',
      3:  'Very poor -- mostly unusable',
      2:  'Bad -- severely broken',
      1:  'Very bad -- barely renders',
      0:  'Broken -- blank or error state',
    },
  },
  dimensions: {
    game_identity: {
      description: 'Game recognition through restrained accent colors and typography (not heavy theming)',
      criteria: [
        'Game identity expressed through accent color (purple for MTG, red for Pokemon, gold for YGO)',
        'Typography conveys game feel (serif for MTG, geometric sans for Pokemon, angular for YGO)',
        'White/light background with game-colored accents -- NOT dark themed',
        'A fan recognizes the game from color + type, not from heavy decoration',
        'Restraint: game theming through 1-2 accent colors, not saturated backgrounds',
      ],
    },
    visual_hierarchy: {
      description: 'Information architecture and scannability',
      criteria: [
        'Card images are the most prominent element',
        'Similarity scores are instantly readable',
        'Card name stands out from metadata',
        'Stat badges (ATK/DEF, P/T, HP) are prominent and game-authentic',
        'Keyword tags and archetype badges are visible but secondary to card name',
        'Oracle text is readable but secondary',
      ],
    },
    typography: {
      description: 'Apple-level type hierarchy: antialiased system fonts, negative letter-spacing on headings, clear weight ramp',
      criteria: [
        'Body text uses system fonts (-apple-system / SF Pro) with -webkit-font-smoothing: antialiased',
        'Card name is the identity signal: game-specific font (Cinzel serif for MTG, Outfit geometric for Pokemon, Crimson Pro for YGO)',
        'Clear weight ramp: 700 for titles, 600 for card names, 400 for body',
        'Similarity percentage is the largest numeric element on each card (22px+, bold, accent-colored)',
        'Metadata is visibly smaller and lighter than card name',
        'No font-size collision: each level of the hierarchy is distinguishable at a glance',
      ],
    },
    whitespace_layout: {
      description: 'Generous whitespace, Apple-style card density',
      criteria: [
        'Generous breathing room between cards (20px+ gap)',
        'Cards feel like they float on the white background',
        'Stat badges, tags, and labels flow naturally without cramping',
        'Consistent padding/margins across elements',
        'Overall feel is spacious and unhurried, not dense or cramped',
      ],
    },
    color_harmony: {
      description: 'Minimal palette: white + 1-2 accent colors per game',
      criteria: [
        'Background is white or near-white (#fafafa range)',
        'Accent color used sparingly: borders, links, similarity %, active states',
        'Text is dark (#1d1d1f range) on light background with clear contrast',
        'Shadows are subtle and neutral (not colored)',
        'No heavy borders, glows, or saturated backgrounds',
      ],
    },
    card_presentation: {
      description: 'Card image framing, data richness, and relevance explanation',
      criteria: [
        'Images are large enough to see card art details (120px+ width)',
        'Image framing is clean: 1px border + layered shadow, not heavy frame decoration',
        'Stat badges visible and game-authentic: ATK/DEF for YGO, P/T for Magic, HP for Pokemon',
        'Archetype/subtype labels present for game-specific classification',
        'Keyword ability tags shown as small pills',
      ],
    },
    modern_polish: {
      description: 'Apple-level production quality and attention to detail',
      criteria: [
        'Layered shadows create realistic depth, not flat single-shadow',
        'Border-radius is consistent: 12px for cards, 8px for badges/tags',
        'Hover states are subtle: lift + shadow increase, not dramatic color changes',
        'No visual clutter: every element earns its space',
        'Status messages and badges use light tinted backgrounds not solid dark ones',
      ],
    },
  },
};

// ---------------------------------------------------------------------------
// Per-game context for VLM prompts
// ---------------------------------------------------------------------------

export const GAME_CONTEXTS = {
  magic: {
    name: 'Magic: The Gathering',
    desc: 'White (#fafafc) background, purple (#7c5cbf) accents, Cinzel serif card names, system font body text, subtle shadows, thin borders. Power/toughness stat badges, keyword ability tags, creature type labels. Apple-inspired minimal layout.',
  },
  pokemon: {
    name: 'Pokemon TCG',
    desc: 'White (#ffffff) background, red (#cc0000) accent, Outfit geometric sans-serif, 12px rounded cards, system font fallbacks, subtle shadows. HP/retreat stat badges, energy type color-coded, set name + regulation mark, subtype labels. Clean Apple-style cards.',
  },
  yugioh: {
    name: 'Yu-Gi-Oh!',
    desc: 'Warm white (#fafaf8) background, gold (#b8993e) accents, Rajdhani uppercase headers, Crimson Pro serif card names, system font body. ATK/DEF stat badges, level indicators, attribute color coding, archetype badges. Minimal Apple-hybrid layout.',
  },
};

// ---------------------------------------------------------------------------
// Context prompt builder (game-specific, rubric handled by library)
// ---------------------------------------------------------------------------

export function gamePrompt(gameKey) {
  const ctx = GAME_CONTEXTS[gameKey];
  if (!ctx) throw new Error(`Unknown game: ${gameKey}`);
  return `You are a senior UI designer reviewing a card game search tool for "${ctx.name}".\n\nCURRENT DESIGN: ${ctx.desc}\n\nIMPORTANT: Look at what IS shown in the screenshot, not what you imagine.`;
}
