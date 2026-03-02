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
import { validateScreenshot, clearCache, getCacheStats } from '@arclabs561/ai-visual-test';
import { existsSync } from 'fs';

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
        'Substitutability badges are scannable',
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
        'Cards have breathing room between them',
        'Image and text columns are well-proportioned',
        'No content feels cramped or overflowing',
        'Consistent padding/margins across elements',
        'Results list doesn\'t feel too dense or too sparse',
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
      description: 'Card image framing and visual treatment',
      criteria: [
        'Images are large enough to see card art details',
        'Border/frame treatment references actual card borders',
        'Image has depth (shadow, subtle glow, or border accent)',
        'Fallback state for missing images looks intentional',
        'Card aspect ratio matches real TCG cards (~2.5:3.5)',
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
// Per-game screenshot config
// ---------------------------------------------------------------------------
const screenshots = [
  {
    path: '/tmp/vlm_magic.png',
    game: 'Magic: The Gathering',
    desc: 'Dark purple-slate (#1e1a2e) background, gold (#c8a84b) accents, Cinzel serif card names, radial gradient, gold card borders with purple glow.',
  },
  {
    path: '/tmp/vlm_pokemon.png',
    game: 'Pokemon TCG',
    desc: 'Light cream (#faf6f0) background, red (#cc0000) accent, yellow (#e0c878) card borders, Outfit geometric sans-serif (rounded/bold), 16px rounded corners, uppercase headers, hover lift.',
  },
  {
    path: '/tmp/vlm_yugioh.png',
    game: 'Yu-Gi-Oh!',
    desc: 'Dark navy (#0a0a18) background, millennium gold (#c9a84c) accents, Rajdhani uppercase headers, Crimson Pro card names, angular borders, diagonal gold line overlay.',
  },
];

// ---------------------------------------------------------------------------
// Prompt builder -- combines game context with rubric dimensions
// ---------------------------------------------------------------------------
function makePrompt(game, desc) {
  // Build the dimension section from the rubric
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
  console.log(`Cache: ${stats.size} entries, ${(stats.hitRate * 100).toFixed(0)}% hit rate`);

  let allPassed = true;

  for (const { path, game, desc } of screenshots) {
    if (!existsSync(path)) {
      console.log(`\nSKIP: ${path} not found`);
      continue;
    }
    console.log(`\n${'='.repeat(60)}`);
    console.log(`EVALUATING: ${game}`);
    console.log('='.repeat(60));

    try {
      const result = await validateScreenshot(path, makePrompt(game, desc), {
        useCache: false,
        modelTier: 'balanced',
        useRubric: true,
        includeDimensions: true,
        description: `DeckSage ${game} theme visual quality`,
        testType: 'visual-quality',
      });

      const score = result.score ?? 0;
      const status = score >= PASS_THRESHOLD ? 'PASS' : 'NEEDS WORK';
      console.log(`\n${status}: ${score}/10 (threshold: ${PASS_THRESHOLD})`);
      if (result.cached) console.log('  (served from cache)');
      if (result.responseTime) console.log(`  Response: ${result.responseTime}ms`);

      // Display dimension scores (from structured JSON extraction)
      if (result.dimensionScores) {
        console.log(`\nDIMENSIONS:`);
        for (const [dim, val] of Object.entries(result.dimensionScores)) {
          const bar = val >= PASS_THRESHOLD ? '+' : '-';
          console.log(`  ${bar} ${dim}: ${val}/10`);
        }
      }

      // Also try to parse dimensionScores from reasoning text as fallback
      if (!result.dimensionScores && result.reasoning) {
        const dimPattern = /"dimensionScores"\s*:\s*\{([^}]+)\}/;
        const match = result.reasoning.match(dimPattern);
        if (match) {
          try {
            const dims = JSON.parse(`{${match[1]}}`);
            console.log(`\nDIMENSIONS (parsed from reasoning):`);
            for (const [dim, val] of Object.entries(dims)) {
              const bar = val >= PASS_THRESHOLD ? '+' : '-';
              console.log(`  ${bar} ${dim}: ${val}/10`);
            }
          } catch { /* ignore parse errors */ }
        }
      }

      if (result.issues?.length) {
        console.log(`\nISSUES (${result.issues.length}):`);
        result.issues.forEach((issue, i) => console.log(`  ${i + 1}. ${issue}`));
      }

      if (result.reasoning) {
        const short = result.reasoning.length > 500
          ? result.reasoning.slice(0, 500) + '...'
          : result.reasoning;
        console.log(`\nREASONING:\n${short}`);
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
