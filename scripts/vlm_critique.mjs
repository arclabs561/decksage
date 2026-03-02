#!/usr/bin/env node
/**
 * VLM-based visual critique of DeckSage frontend screenshots.
 * Uses @arclabs561/ai-visual-test with rubric scoring and cache bypass.
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

const screenshots = [
  { path: '/tmp/vlm_magic.png', game: 'Magic: The Gathering',
    desc: 'Dark purple-slate background, gold (#c8a84b) accents, Cinzel serif card names, radial gradient, gold card borders with purple glow.' },
  { path: '/tmp/vlm_pokemon.png', game: 'Pokemon TCG',
    desc: 'Light cream (#faf6f0) background, red (#cc0000) accent, yellow (#e0c878) card borders, Nunito sans-serif, rounded 12px corners, playful feel.' },
  { path: '/tmp/vlm_yugioh.png', game: 'Yu-Gi-Oh!',
    desc: 'Dark navy (#0a0a18) background, millennium gold (#c9a84c) accents, Rajdhani headers uppercase, Crimson Pro card names, angular borders, diagonal gold line overlay.' },
];

function makePrompt(game, desc) {
  return `You are a senior UI designer reviewing a card game search tool for "${game}".

CURRENT DESIGN: ${desc}

Evaluate strictly on these 7 dimensions. For each, give a score 0-10 and ONE specific actionable fix (CSS property + value):

1. GAME AUTHENTICITY: Does this match how the actual ${game} brand looks? Compare to official ${game} websites/apps.
2. VISUAL HIERARCHY: Card image prominence, similarity score readability, metadata scannability.
3. TYPOGRAPHY: Font appropriateness for this game, readability, size.
4. SPACING & LAYOUT: Whitespace balance, card density, visual breathing room.
5. COLOR HARMONY: Color palette cohesion, contrast ratios, text readability.
6. CARD IMAGE PRESENTATION: Image framing, border treatment, size relative to card, hover effects.
7. MODERN POLISH: Professional feel, transitions, shadow depth, overall production quality.

IMPORTANT: Look at what IS shown, not what you imagine. Describe specific elements you see.
Give an overall score 0-10 and a ranked list of the top 3 most impactful CSS changes.`;
}

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

      if (result.issues?.length) {
        console.log(`\nISSUES (${result.issues.length}):`);
        result.issues.forEach((issue, i) => console.log(`  ${i + 1}. ${issue}`));
      }

      if (result.reasoning) {
        // Truncate reasoning to first 500 chars for console
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
