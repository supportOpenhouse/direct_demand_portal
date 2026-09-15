#!/usr/bin/env node
/* Theme guard. Dark mode is only as complete as the last literal that was missed,
   so this is the one mechanical proof that the token migration actually landed.

   Three checks:
     1. no raw colour in app.css outside the token blocks
     2. no raw colour in any .ts/.tsx
     3. every var(--x) used is defined somewhere

   Comments are stripped BEFORE scanning. app.css has comments that EXPLAIN colour
   ("the rail is #111a2b, so the black has to be lifted") — prose naming a hex is not
   paint, and a guard that can't tell the difference fails on its own documentation. */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname;
const CSS = join(ROOT, 'src/styles/app.css');
const SRC = join(ROOT, 'src');

const COLOUR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(/g;

/* Blank out comment bodies, keeping newlines so line numbers survive. */
const blank = (s) => s.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
const blankLine = (s) => s.replace(/\/\/.*$/, (m) => ' '.repeat(m.length));

/* A declaration block is a token block when its selector is only :root, [data-theme=…]
   or [data-accent=…] — those are the three places a raw colour is allowed to exist. */
/* A unit is :root or a CHAIN of the theme/accent attributes — the dark+orange
   pairing is written `[data-theme='dark'][data-accent='orange']`, one selector, and
   a pattern allowing only a single attribute rejected it as raw colour. */
const UNIT = "(?::root|(?:\\[data-(?:theme|accent)=['\"][a-z]+['\"]\\])+)";
const TOKEN_SELECTOR = new RegExp(`^[\\s,]*${UNIT}(?:\\s*,\\s*${UNIT})*\\s*$`);

function cssTokenRanges(text) {
  const ranges = [];
  const re = /(^|\}|\*\/)([^{}]*)\{/g;
  let m;
  while ((m = re.exec(text))) {
    if (!TOKEN_SELECTOR.test(m[2])) continue;
    const open = re.lastIndex - 1;
    let depth = 0;
    for (let i = open; i < text.length; i++) {
      if (text[i] === '{') depth++;
      else if (text[i] === '}' && --depth === 0) { ranges.push([open, i]); break; }
    }
  }
  return ranges;
}

/* Attribute a violation to the nearest preceding banner comment, so a task can ask
   "is MY section clean?" without tracking line numbers that shift under every edit. */
function sections(text) {
  const out = [];
  const re = /\/\*([\s\S]*?)\*\//g;
  let m;
  while ((m = re.exec(text))) {
    const label = m[1].split('\n').map((l) => l.replace(/[-=─\s*]/g, ' ').trim())
      .find((l) => /[A-Za-z]/.test(l));
    if (label) out.push({ at: m.index, label: label.slice(0, 46) });
  }
  return out;
}

const lineOf = (text, i) => text.slice(0, i).split('\n').length;

function walk(dir, out = []) {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(n)) out.push(p);
  }
  return out;
}

/* Escape hatch. A line carrying `theme-exempt` — or sitting inside a
   `theme-exempt:start` … `theme-exempt:end` fence — is skipped. It exists for
   colour that must NOT follow the theme: a brand mark, or a poster that
   html2canvas rasterises for sharing (a dark-mode export nobody wants to send).
   Requiring the marker in the source keeps every exemption visible and argued. */
function exemptLines(text) {
  const out = new Set();
  let fenced = false;
  text.split('\n').forEach((l, i) => {
    if (/theme-exempt:start/.test(l)) fenced = true;
    if (fenced || /theme-exempt/.test(l)) out.add(i + 1);
    if (/theme-exempt:end/.test(l)) fenced = false;
  });
  return out;
}

const bad = [];
const raw = readFileSync(CSS, 'utf8');
const scan = blank(raw);
const allowed = cssTokenRanges(scan);
const banners = sections(raw);
const cssExempt = exemptLines(raw);

for (const m of scan.matchAll(COLOUR)) {
  if (allowed.some(([a, b]) => m.index > a && m.index < b)) continue;
  const s = [...banners].reverse().find((x) => x.at < m.index);
  if (cssExempt.has(lineOf(raw, m.index))) continue;
  bad.push({ file: 'src/styles/app.css', line: lineOf(raw, m.index), value: m[0], section: s ? s.label : '(top of file)' });
}

for (const f of walk(SRC)) {
  const t = readFileSync(f, 'utf8');
  const s = blank(t).split('\n').map(blankLine).join('\n');
  const ex = exemptLines(t);
  for (const m of s.matchAll(/#[0-9a-fA-F]{3,8}\b/g)) {
    if (ex.has(lineOf(t, m.index))) continue;
    bad.push({ file: relative(ROOT, f), line: lineOf(t, m.index), value: m[0], section: 'tsx' });
  }
}

/* every var(--x) has a definition */
const defined = new Set([...raw.matchAll(/(--[a-z0-9-]+)\s*:/gi)].map((m) => m[1]));
for (const f of [CSS, ...walk(SRC)]) {
  const t = blank(readFileSync(f, 'utf8'));
  for (const m of t.matchAll(/var\(\s*(--[a-z0-9-]+)/gi)) {
    if (!defined.has(m[1]) && !/--bv-|--acc|--snap/.test(m[1]))
      bad.push({ file: relative(ROOT, f), line: lineOf(t, m.index), value: `var(${m[1]}) undefined`, section: 'undefined-token' });
  }
}

/* The hex hunt alone can be satisfied by DELETING the colours: a global rewrite
   that turned `--emerald:#059669` into `--emerald:var(--emerald)` passed it once.
   So also assert the property — every token resolves to a real literal, and the
   dark block actually redefines the core surfaces. */
function tokenBlock(re_) {
  const m = scan.match(re_);
  if (!m) return null;
  const open = m.index + m[0].length - 1;
  let depth = 0;
  for (let i = open; i < scan.length; i++) {
    if (scan[i] === '{') depth++;
    else if (scan[i] === '}' && --depth === 0) return raw.slice(open, i);
  }
  return null;
}
const parse = (b) => Object.fromEntries([...(b || '').matchAll(/(--[a-z0-9-]+)\s*:\s*([^;}]+)/gi)].map((m) => [m[1], m[2].trim()]));
const light = parse(tokenBlock(/:root[^{}]*\{/));
const dark  = parse(tokenBlock(/\[data-theme=['"]dark['"]\][^{}]*\{/));

for (const [k, v] of Object.entries(light)) {
  // (?![\w-]) not \b: a hyphen is a non-word char, so `\b` after `--stripe-emerald`
  // matches inside `var(--stripe-emerald-band)` and reports a false self-reference.
  if (new RegExp(`var\\(\\s*${k}(?![\\w-])`).test(v))
    bad.push({ file: 'src/styles/app.css', line: 0, value: `${k} references itself`, section: 'self-reference' });
}
for (const [k] of Object.entries(light)) {
  let v = light[k], hops = 0;
  while (/^var\(/.test(v) && hops++ < 10) v = light[(v.match(/var\(\s*(--[a-z0-9-]+)/) || [])[1]] ?? '';
  if (!v) bad.push({ file: 'src/styles/app.css', line: 0, value: `${k} resolves to nothing`, section: 'empty-token' });
}
for (const k of ['--bg', '--panel', '--panel-2', '--ink', '--ink-2', '--line', '--brand', '--sidebar-bg', '--on-accent'])
  if (!(k in dark)) bad.push({ file: 'src/styles/app.css', line: 0, value: `${k} has no dark value`, section: 'half-dark' });

const only = process.argv.includes('--section')
  ? process.argv[process.argv.indexOf('--section') + 1].toLowerCase() : null;
const shown = only ? bad.filter((b) => b.section.toLowerCase().includes(only)) : bad;

if (!shown.length) {
  console.log(only ? `theme guard: section "${only}" clean` : 'theme guard: clean');
  process.exit(0);
}
const grouped = new Map();
for (const b of shown) grouped.set(b.section, [...(grouped.get(b.section) || []), b]);
for (const [sec, items] of [...grouped].sort((a, b) => b[1].length - a[1].length)) {
  console.log(`\n  ${sec}  —  ${items.length}`);
  for (const i of items.slice(0, 6)) console.log(`      ${i.file}:${i.line}  ${i.value}`);
  if (items.length > 6) console.log(`      … ${items.length - 6} more`);
}
console.log(`\ntheme guard: ${shown.length} violation(s)\n`);
process.exit(1);
