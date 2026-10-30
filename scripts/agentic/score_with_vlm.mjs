#!/usr/bin/env node
/**
 * Score one agentic session's screenshots with ai-visual-test.
 *
 * The journeys in use_site.py answer "did it work"; this answers "did it look
 * finished". Scores and issues are appended to the session note so a later run
 * can show a delta rather than an opinion.
 *
 * Usage:
 *   node scripts/agentic/score_with_vlm.mjs .agents/reports/agentic-sessions/<session>.json
 *
 * Environment: VLM_PROVIDER and VLM_MODEL, read from ../.env when unset.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, resolve, basename } from 'node:path';

const PKG_CANDIDATES = [
  '/Users/arc/Developer/ai-visual-test/build/src/index.js',
  resolve(process.cwd(), 'node_modules/@arclabs561/ai-visual-test/build/src/index.js'),
];
const pkgPath = PKG_CANDIDATES.find((p) => existsSync(p));
if (!pkgPath) {
  console.error('ai-visual-test build not found; install it or point PKG_CANDIDATES at one');
  process.exit(2);
}
const { validateScreenshot } = await import(pkgPath);

// .env beside the repo root
const root = resolve(dirname(new URL(import.meta.url).pathname), '../..');
const envPath = resolve(root, '.env');
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, 'utf8').split('\n')) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const i = t.indexOf('=');
    if (i > 0) {
      const k = t.slice(0, i).trim();
      if (!process.env[k]) process.env[k] = t.slice(i + 1).trim();
    }
  }
}
const provider = process.env.VLM_PROVIDER || 'openrouter';
const model = process.env.VLM_MODEL || 'google/gemini-3.8-flash';

const RUBRIC = {
  'land-phone':
    'A mobile landing page for a card similarity tool. Judge hierarchy and finish: is there one obvious action, ' +
    'do type sizes and spacing read as one system, does anything look like an unstyled default widget, is any control ' +
    'ambiguous about whether it is selected. Name concrete defects with their location.',
  'search-name-phone':
    'Mobile search results for similar cards. Judge readability: can you tell the query card from the results, ' +
    'is match strength legible, is card art consistently sized, does anything wrap badly or crowd.',
  'search-description-phone':
    'Mobile results for a described effect rather than a card name. Judge whether the page explains what it searched ' +
    'and whether an empty or weak result set is handled honestly.',
  'deck-tab-phone':
    'Mobile deck building form: seed chips, a deck textarea, a format toggle, a primary action. Judge alignment, ' +
    'label placement, and whether one action clearly leads.',
  'build-deck-phone':
    'A generated deck list on mobile. Judge scannability of the list, whether counts and names align, and whether ' +
    'anything looks like raw output dumped into the page.',
  'review-desktop':
    'Desktop annotation review page. Judge whether it belongs to the same product as a dark, gold-accented search ' +
    'page: type hierarchy, control alignment, empty-state guidance, spacing.',
};

const input = process.argv[2];
if (!input) {
  console.error('usage: score_with_vlm.mjs <session.json>');
  process.exit(2);
}
const session = JSON.parse(readFileSync(input, 'utf8'));
const baseDir = resolve(dirname(input));

const scores = [];
for (const step of session.steps) {
  const rubric = RUBRIC[step.step];
  if (!rubric || !step.shot) continue;
  const image = resolve(root, step.shot);
  if (!existsSync(image)) continue;
  try {
    const r = await validateScreenshot(image, rubric, { provider, model });
    scores.push({ step: step.step, score: r.score, issues: r.issues || [], recommendations: r.recommendations || [] });
    console.log(`${step.step}: ${r.score ?? 'null'} (${(r.issues || []).length} issues)`);
  } catch (err) {
    scores.push({ step: step.step, error: String(err.message).slice(0, 200) });
    console.log(`${step.step}: FAILED ${String(err.message).slice(0, 120)}`);
  }
}

const out = input.replace(/\.json$/, '.scores.json');
writeFileSync(out, JSON.stringify({ provider, model, at: new Date().toISOString(), scores }, null, 2) + '\n');

// append a human section to the note beside the json
const notePath = input.replace(/\.json$/, '.md');
if (existsSync(notePath)) {
  const lines = ['', '## Visual scores (ai-visual-test)', '', `Model: \`${provider}/${model}\`.`, '', '| step | score | top issues |', '|---|---|---|'];
  for (const s of scores) {
    if (s.error) {
      lines.push(`| ${s.step} | — | failed: ${s.error} |`);
      continue;
    }
    const top = (s.issues || []).slice(0, 3).join('; ').replace(/\|/g, '/');
    lines.push(`| ${s.step} | ${s.score ?? 'null'} | ${top} |`);
  }
  lines.push('');
  writeFileSync(notePath, readFileSync(notePath, 'utf8') + lines.join('\n'));
}

console.log(`wrote ${basename(out)}`);
