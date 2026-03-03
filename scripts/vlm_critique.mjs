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
      10: 'Perfect -- indistinguishable from an official card game app',
      9:  'Excellent -- polished, brand-appropriate, minor cosmetic nit',
      8:  'Very good -- clearly themed, readable, small spacing issues',
      7:  'Good -- recognizable game aesthetic, functional layout',
      6:  'Acceptable -- generic look, missing game identity cues',
      5:  'Needs work -- poor contrast, wrong font feel, cramped',
      4:  'Poor -- broken layout, illegible text, no game theming',
      3:  'Very poor -- mostly unusable',
      2:  'Bad -- severely broken',
      1:  'Very bad -- barely renders',
      0:  'Broken -- blank or error state',
    },
  },
  dimensions: {
    game_authenticity: {
      description: 'How well the UI matches the official card game brand',
      criteria: [
        'Color palette matches official game websites/apps',
        'Typography feels appropriate for this game\'s identity',
        'Card frame/border treatment references real card designs',
        'Overall mood matches the game (dark/mystical for MTG, playful for Pokemon, angular/gold for YGO)',
        'Would a fan of this game recognize the theme immediately?',
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
      description: 'Font choice, sizing, weight, and readability',
      criteria: [
        'Header font suits the game aesthetic',
        'Card name font is bold and legible',
        'Metadata font is clearly smaller/lighter than card name',
        'Similarity percentage is large and contrasty',
        'Font sizes create clear hierarchy (H1 > card name > meta > oracle)',
      ],
    },
    spacing_layout: {
      description: 'Whitespace balance and card density',
      criteria: [
        'Cards have generous breathing room between them (18px+ gap)',
        'Image and text columns are well-proportioned',
        'Stat badges, tags, and archetype labels flow naturally without cramping',
        'Consistent padding/margins across elements',
        'Results list density is comfortable for cards with rich metadata',
      ],
    },
    color_harmony: {
      description: 'Palette cohesion, contrast ratios, text legibility',
      criteria: [
        'Accent colors complement the background',
        'Text has sufficient contrast for readability',
        'Card borders/shadows use game-appropriate tones',
        'Hover/active states use accent colors consistently',
        'No jarring color clashes',
      ],
    },
    card_presentation: {
      description: 'Card image framing and data richness',
      criteria: [
        'Images are large enough to see card art details',
        'Border/frame treatment references actual card borders',
        'Image has depth (shadow, subtle glow, or border accent)',
        'Stat badges visible: ATK/DEF for YGO, P/T for Magic, HP for Pokemon',
        'Archetype/subtype labels present for game-specific classification',
        'Keyword ability tags shown as small colored pills',
        'Click-to-expand chevron hints at more detail',
      ],
    },
    modern_polish: {
      description: 'Production quality and interaction design',
      criteria: [
        'Hover effects feel responsive',
        'Shadows give appropriate depth',
        'Transitions are smooth, not jarring',
        'Overall feel is professional, not amateur',
        'Consistent border-radius and spacing system',
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
    domain: 'Trading card game search & similarity tool (Magic, Pokemon, Yu-Gi-Oh)',
    positive: [
      'Card images large enough to see art details (120px+ width)',
      'Game-appropriate color palette matching official brand',
      'Typography hierarchy: header > card name > stats > metadata > oracle text',
      'Card aspect ratio close to real TCG cards (~2.5:3.5)',
      'Generous whitespace between card results (18px+ gap)',
      'Stat badges (ATK/DEF, P/T, HP) prominently displayed in game-authentic style',
      'Keyword ability tags as small colored pills',
      'Similarity percentage large and high-contrast',
      'Smooth hover transitions and depth via shadows',
    ],
    negative: [
      'Generic unthemed styling with no game identity',
      'Cramped layout with overlapping or truncated text',
      'Missing card images with no fallback or broken placeholder',
      'Insufficient text contrast against colored backgrounds',
      'Jarring color clashes between accent and background',
      'All text same size/weight (no visual hierarchy)',
      'Card stats or metadata missing entirely',
      'No hover or interaction feedback',
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
    desc: 'Dark purple-slate (#1e1a2e) background, gold (#c8a84b) accents, Cinzel serif card names, radial gradient, gold card borders with purple glow. Power/toughness stat badges, keyword ability tags (Flying, Haste), creature type labels, expand chevron.',
  },
  {
    path: '/tmp/vlm_pokemon.png',
    game: 'Pokemon TCG',
    gameKey: 'pokemon',
    desc: 'Light cream (#faf6f0) background, red (#cc0000) accent, yellow (#e0c878) card borders, Outfit geometric sans-serif (rounded/bold), 10px rounded corners, uppercase headers, hover lift. HP/retreat stat badges, energy type color-coded left borders, set name + regulation mark, subtype labels.',
  },
  {
    path: '/tmp/vlm_yugioh.png',
    game: 'Yu-Gi-Oh!',
    gameKey: 'yugioh',
    desc: 'Dark navy (#0a0a18) background, millennium gold (#c9a84c) accents, Rajdhani uppercase headers, Crimson Pro card names, angular borders, diagonal gold line overlay. ATK/DEF stat badges, level indicators, attribute color coding (DARK=purple, FIRE=red), archetype badges in gold border, expand chevron.',
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
- "dimensionScores": {"game_authenticity": N, "visual_hierarchy": N, "typography": N, "spacing_layout": N, "color_harmony": N, "card_presentation": N, "modern_polish": N}
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
            text: `Original ${game} art style -- the UI should evoke this aesthetic`,
            image: ART_REF[gameKey],
            dimension: 'game_authenticity',
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
      const semantic = result.semantic || {};

      if (result.dimensionScores) {
        console.log(`\nDIMENSIONS:`);
        for (const [dim, val] of Object.entries(result.dimensionScores)) {
          const bar = val >= PASS_THRESHOLD ? '+' : '-';
          console.log(`  ${bar} ${dim}: ${val}/10`);
        }
      }

      // Rich issues with importance + evidence
      const issues = semantic.issues || result.issues || [];
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
      const recs = semantic.recommendations || [];
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
      const strengths = semantic.strengths || [];
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
