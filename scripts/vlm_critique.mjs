#!/usr/bin/env node
/**
 * VLM-based visual critique of DeckSage frontend screenshots.
 * Uses @arclabs561/ai-visual-test with a custom rubric tuned for
 * card-game UI evaluation.
 *
 * Prerequisites:
 *   - Screenshots at /tmp/vlm_{magic,pokemon,yugioh}.png
 *     (taken by Playwright during QA or manually via `webshot`)
 *   - GEMINI_API_KEY or OPENAI_API_KEY or ANTHROPIC_API_KEY in env
 *
 * Usage:
 *   node scripts/vlm_critique.mjs            # evaluate all 3 themes
 *   node scripts/vlm_critique.mjs --clear    # clear cache first
 */
import { readFileSync, existsSync } from 'fs';
import { validateScreenshot, createConfig, clearCache, getCacheStats } from '@arclabs561/ai-visual-test';

// Load .env (lightweight, no dependency needed)
try {
  const envPath = new URL('../.env', import.meta.url).pathname;
  for (const line of readFileSync(envPath, 'utf8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx > 0) {
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim();
      if (!process.env[key]) process.env[key] = val;
    }
  }
} catch { /* .env optional */ }

const PASS_THRESHOLD = 7;

// ---------------------------------------------------------------------------
// Custom rubric: 7 dimensions specific to card-game search UIs.
// This replaces the default (visual/functional/usability/accessibility)
// rubric with game-specific criteria that drive actionable CSS fixes.
// ---------------------------------------------------------------------------
const CARD_GAME_RUBRIC = {
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
        'Clear weight ramp: 700 for titles, 600 for card names, 400 for body, never 300 or 800 for body',
        'Similarity percentage is the largest numeric element on each card (22px+, bold, accent-colored)',
        'Metadata is visibly smaller and lighter than card name (14px regular vs 18-20px semibold)',
        'Letter-spacing: slight negative (-0.01em to -0.02em) on large text, neutral on body, slight positive (0.02em+) on small caps/labels',
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
        'Keyword ability tags shown as small pills (11px, rounded)',
        '"Why similar" snippet visible on results explaining the match reason with signal chips',
        'Expand chevron hints at more detail; substitutability badge shows practical value',
      ],
    },
    modern_polish: {
      description: 'Apple-level production quality and attention to detail',
      criteria: [
        'Layered shadows (2+ layers, opacity 0.04-0.08) create realistic depth, not flat single-shadow',
        'Border-radius is consistent: 12px for cards and search, 8px for badges/tags, 4px for inner elements',
        'Hover states are subtle: translateY(-2px) lift + shadow increase, not dramatic color changes',
        'Transitions are property-specific (background 0.15s, shadow 0.3s) not "all 0.3s"',
        'No visual clutter: every element earns its space -- if removing it loses no information, it should go',
        'Focus states use ring pattern (0 0 0 4px rgba(accent, 0.12)) not thick outlines',
        'Status messages, badges, and alerts use light tinted backgrounds (rgba 0.08) not solid dark backgrounds',
      ],
    },
  },
};

// ---------------------------------------------------------------------------
// Reference image paths (relative to decksage repo root)
// Art style refs: canonical original art that defines each game's aesthetic
// UI refs: gold-standard card database interfaces
// ---------------------------------------------------------------------------
const REF = new URL('../qa/reference/', import.meta.url).pathname;

const ART_REF = {
  magic:   `${REF}mtg-serra-angel-card.jpg`,        // Douglas Shuler oil painting + card frame
  pokemon: `${REF}pokemon-sugimori-watercolor.png`,  // Ken Sugimori 1996 watercolor
  yugioh:  `${REF}yugioh-dark-magician-takahashi.png`, // Kazuki Takahashi manga (Duel Art)
};

const UI_REF = {
  magic:   `${REF}ui-scryfall-search.png`,           // Scryfall card grid
  pokemon: `${REF}ui-pkmncards-search.png`,           // pkmncards.com search
  yugioh:  `${REF}ui-yugioh-official-db.png`,         // Konami official card DB
};

// ---------------------------------------------------------------------------
// Config with domain-level visual anchors (v0.7.2)
//
// Shared text anchors apply to all games. Game-specific image anchors are
// passed per-screenshot via context.anchors (merged at call time).
// ---------------------------------------------------------------------------
const config = createConfig({
  provider: 'gemini',  // Vision-capable provider required for image anchors
  anchors: {
    domain: 'Card similarity search tool -- Apple-minimal design (white bg, 12px radius cards, layered shadows, system fonts, game-specific accent color)',
    positive: [
      // Layout & spacing (Apple 8px grid)
      'White or near-white background (#f5f5f7 / #fafafa range)',
      'Cards have 12px border-radius, 1px borders, layered box-shadow (0.04-0.06 opacity)',
      'Generous padding inside cards (20px+) and 12px+ gap between cards',
      'Cards float on the background -- no heavy decoration, breathing room everywhere',
      // Typography
      'System font stack (-apple-system / SF Pro) for body; game-specific font for card names only',
      '5-level type hierarchy: page title > card name (17-20px semibold) > stats (13px bold) > metadata (14px) > oracle/muted (13px)',
      'Similarity percentage is the largest number on the card (22px+, bold, accent-colored)',
      // Data richness per card
      'Each result card shows: card image, name, similarity %, stat badges (ATK/DEF or P/T or HP), keyword tags, "Why similar" snippet with signal chips',
      'Query card banner at top with image + metadata -- user knows what they searched for',
      '"Why similar" snippet below each result explains the match (e.g. "Both have Flying", "Same archetype")',
      // Interaction cues
      'Expand chevron on each card hints at more detail',
      'Hover lifts card (translateY -2px) with subtle shadow increase',
      'Search form has 12px radius, focus ring (4px accent-colored outline)',
      // Color discipline
      'Game accent color used only for: links, similarity %, active borders, accent bar, button CTA',
      'Text is dark (#1d1d1f) on light bg; secondary text is #6e6e73; muted is #86868b',
    ],
    negative: [
      'Dark themed backgrounds (dark purple, dark navy, black) -- these are explicitly wrong',
      'Heavy borders (>1px), colored glows, text-shadows, drop-shadows with opacity > 0.15',
      'Cramped layout: cards touching, text truncated, no padding between elements',
      'Missing card images with no fallback or broken image placeholder',
      'Flat hierarchy: all text same size/weight, nothing stands out',
      'Saturated colored backgrounds on cards or result containers',
      'Decorative noise: diagonal patterns, radial gradients, animated backgrounds',
      'Generic result cards with no game-specific data (no stats, no keywords, no type info)',
      '"Why similar" snippet saying only "Shared type: creature" for every card (too generic)',
      'Search results that give no hint WHY they matched -- user must guess relevance',
    ],
  },
});

// ---------------------------------------------------------------------------
// Per-game screenshot config
// ---------------------------------------------------------------------------
const screenshots = [
  {
    path: '/tmp/vlm_magic.png',
    game: 'Magic: The Gathering',
    gameKey: 'magic',
    desc: 'White (#fafafc) background, purple (#7c5cbf) accents, Cinzel serif card names, system font body text, subtle shadows, thin borders. Power/toughness stat badges, keyword ability tags, creature type labels, expand chevron. Apple-inspired minimal layout.',
  },
  {
    path: '/tmp/vlm_pokemon.png',
    game: 'Pokemon TCG',
    gameKey: 'pokemon',
    desc: 'White (#ffffff) background, red (#cc0000) accent, Outfit geometric sans-serif, 12px rounded cards, system font fallbacks, subtle shadows. HP/retreat stat badges, energy type color-coded, set name + regulation mark, subtype labels. Clean Apple-style cards.',
  },
  {
    path: '/tmp/vlm_yugioh.png',
    game: 'Yu-Gi-Oh!',
    gameKey: 'yugioh',
    desc: 'Warm white (#fafaf8) background, gold (#b8993e) accents, Rajdhani uppercase headers, Crimson Pro serif card names, system font body. ATK/DEF stat badges, level indicators, attribute color coding, archetype badges, expand chevron. Minimal Apple-hybrid layout.',
  },
];

// ---------------------------------------------------------------------------
// Prompt builder -- per-screenshot context + rubric dimensions
//
// Domain-level anchors are now in config (injected automatically).
// This function only needs the game-specific context and rubric structure.
// ---------------------------------------------------------------------------
function makePrompt(game, desc) {
  const dimSection = Object.entries(CARD_GAME_RUBRIC.dimensions)
    .map(([key, dim], i) => {
      const name = key.replace(/_/g, ' ').toUpperCase();
      return `${i + 1}. ${name}: ${dim.description}\n${dim.criteria.map(c => `   - ${c}`).join('\n')}`;
    })
    .join('\n\n');

  return `You are a senior UI designer reviewing a card game search tool for "${game}".

CURRENT DESIGN: ${desc}

Evaluate strictly on these 7 dimensions. For each, give a score 0-10 and ONE specific actionable CSS fix:

${dimSection}

IMPORTANT: Look at what IS shown in the screenshot, not what you imagine.

Respond with a JSON object containing:
- "score": overall 0-10 integer
- "dimensionScores": {"game_identity": N, "visual_hierarchy": N, "typography": N, "whitespace_layout": N, "color_harmony": N, "card_presentation": N, "modern_polish": N}
- "issues": array of strings (top issues)
- "reasoning": brief text explaining the score
- "recommendations": array of {priority, suggestion, expectedImpact} objects (top 3 CSS changes)`;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  if (process.argv.includes('--clear')) {
    clearCache();
    console.log('Cache cleared.');
  }

  const stats = getCacheStats();
  console.log(`Cache: ${stats.size} entries`);
  console.log(`Config: provider=${config.provider}, anchors=${config.anchors ? 'yes' : 'no'}`);

  let allPassed = true;

  for (const { path, game, gameKey, desc } of screenshots) {
    if (!existsSync(path)) {
      console.log(`\nSKIP: ${path} not found`);
      continue;
    }
    console.log(`\n${'='.repeat(60)}`);
    console.log(`EVALUATING: ${game}`);
    console.log('='.repeat(60));

    try {
      // Per-game image anchors: art style + UI reference, dimension-scoped.
      // These merge with the shared text anchors from config.
      const gameAnchors = {
        positive: [
          {
            text: `Original ${game} art style -- accent colors should reference this palette`,
            image: ART_REF[gameKey],
            dimension: 'game_identity',
          },
          {
            text: `Gold-standard ${game} card database UI for layout/hierarchy reference`,
            image: UI_REF[gameKey],
            dimension: 'visual_hierarchy',
          },
        ],
      };

      const result = await validateScreenshot(path, makePrompt(game, desc), {
        useCache: false,
        modelTier: 'balanced',
        useRubric: true,
        includeDimensions: true,
        description: `DeckSage ${game} theme visual quality`,
        testType: 'visual-quality',
        anchors: gameAnchors,
      });

      const score = result.score ?? 0;
      const status = score >= PASS_THRESHOLD ? 'PASS' : 'NEEDS WORK';
      console.log(`\n${status}: ${score}/10 (threshold: ${PASS_THRESHOLD})`);
      if (result.cached) console.log('  (served from cache)');
      if (result.responseTime) console.log(`  Response: ${result.responseTime}ms`);

      // Structured output: dimensions, issues, recommendations, reasoning
      // Uses top-level richIssues/recommendations/strengths (v0.7.4+)

      if (result.dimensionScores) {
        console.log(`\nDIMENSIONS:`);
        for (const [dim, val] of Object.entries(result.dimensionScores)) {
          const bar = val >= PASS_THRESHOLD ? '+' : '-';
          console.log(`  ${bar} ${dim}: ${val}/10`);
        }
      }

      // Rich issues with importance + evidence (top-level since v0.7.4)
      const issues = result.richIssues || result.issues || [];
      if (issues.length) {
        console.log(`\nISSUES (${issues.length}):`);
        for (const issue of issues) {
          if (typeof issue === 'object') {
            const imp = issue.importance ? ` [${issue.importance}]` : '';
            const ev = issue.evidence ? `\n       Evidence: ${issue.evidence}` : '';
            const fix = issue.suggestion ? `\n       Fix: ${issue.suggestion}` : '';
            console.log(`  - ${issue.description}${imp}${ev}${fix}`);
          } else {
            console.log(`  - ${issue}`);
          }
        }
      }

      // Actionable recommendations with priority + expected impact
      const recs = result.recommendations || [];
      if (recs.length) {
        console.log(`\nRECOMMENDATIONS:`);
        for (const rec of recs) {
          if (typeof rec === 'object') {
            const pri = rec.priority ? `[${rec.priority}]` : '';
            const impact = rec.expectedImpact ? ` -> ${rec.expectedImpact}` : '';
            console.log(`  ${pri} ${rec.suggestion}${impact}`);
          } else {
            console.log(`  - ${rec}`);
          }
        }
      }

      // Strengths (what's already working well)
      const strengths = result.strengths || [];
      if (strengths.length) {
        console.log(`\nSTRENGTHS:`);
        strengths.forEach(s => console.log(`  + ${s}`));
      }

      if (result.reasoning) {
        console.log(`\nREASONING:\n${result.reasoning}`);
      }

      if (score < PASS_THRESHOLD) allPassed = false;
    } catch (err) {
      console.error(`ERROR: ${err.message}`);
      allPassed = false;
    }
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log(`SUMMARY: ${allPassed ? 'ALL PASS' : 'SOME NEED WORK'} (threshold: ${PASS_THRESHOLD}/10)`);
  process.exit(allPassed ? 0 : 1);
}

main();
