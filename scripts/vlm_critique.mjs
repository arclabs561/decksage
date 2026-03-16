#!/usr/bin/env node
/**
 * VLM-based visual critique of DeckSage frontend screenshots.
 * Uses @arclabs561/ai-visual-test with the shared card-game rubric.
 *
 * Prerequisites:
 *   - Screenshots at /tmp/vlm_{magic,pokemon,yugioh}.png
 *     (taken by Playwright during QA or manually via `webshot`)
 *   - API key in env (auto-loaded from ../.env)
 *
 * Usage:
 *   node scripts/vlm_critique.mjs            # evaluate all 3 themes
 *   node scripts/vlm_critique.mjs --clear    # clear cache first
 */
import { readFileSync, existsSync } from 'fs';
import { validateWithRubric, clearCache, getCacheStats } from '@arclabs561/ai-visual-test';
import { PASS_THRESHOLD, CARD_GAME_RUBRIC, GAME_CONTEXTS, gamePrompt } from '../tests/e2e/vlm-rubric.mjs';

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

// ---------------------------------------------------------------------------
// Reference image paths (for rich critique with art/UI anchors)
// ---------------------------------------------------------------------------
const REF = new URL('../qa/reference/', import.meta.url).pathname;

const ART_REF = {
  magic:   `${REF}mtg-serra-angel-card.jpg`,
  pokemon: `${REF}pokemon-sugimori-watercolor.png`,
  yugioh:  `${REF}yugioh-dark-magician-takahashi.png`,
};

const UI_REF = {
  magic:   `${REF}ui-scryfall-search.png`,
  pokemon: `${REF}ui-pkmncards-search.png`,
  yugioh:  `${REF}ui-yugioh-official-db.png`,
};

// ---------------------------------------------------------------------------
// Per-game screenshot config
// ---------------------------------------------------------------------------
const screenshots = Object.entries(GAME_CONTEXTS).map(([key, ctx]) => ({
  path: `/tmp/vlm_${key}.png`,
  game: ctx.name,
  gameKey: key,
  desc: ctx.desc,
}));

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

  let allPassed = true;

  for (const { path, game, gameKey } of screenshots) {
    if (!existsSync(path)) {
      console.log(`\nSKIP: ${path} not found`);
      continue;
    }
    console.log(`\n${'='.repeat(60)}`);
    console.log(`EVALUATING: ${game}`);
    console.log('='.repeat(60));

    try {
      // Per-game image anchors: art style + UI reference
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

      const result = await validateWithRubric(
        path,
        gamePrompt(gameKey),
        CARD_GAME_RUBRIC,
        { testType: 'visual-quality', anchors: gameAnchors },
        { enforceZeroTolerance: false },
      );

      const score = result.score ?? 0;
      const status = score >= PASS_THRESHOLD ? 'PASS' : 'NEEDS WORK';
      console.log(`\n${status}: ${score}/10 (threshold: ${PASS_THRESHOLD})`);
      if (result.cached) console.log('  (served from cache)');
      if (result.responseTime) console.log(`  Response: ${result.responseTime}ms`);

      if (result.dimensionScores) {
        console.log(`\nDIMENSIONS:`);
        for (const [dim, val] of Object.entries(result.dimensionScores)) {
          const bar = val >= PASS_THRESHOLD ? '+' : '-';
          console.log(`  ${bar} ${dim}: ${val}/10`);
        }
      }

      // Rich issues with importance + evidence
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

      // Actionable recommendations
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

      // Strengths
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
