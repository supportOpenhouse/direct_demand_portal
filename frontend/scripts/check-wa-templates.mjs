#!/usr/bin/env node
/* The template form's two client-side checks, pinned to the SERVER through one table of cases.

   src/lib/api.ts `templateVars` / `isGupshupTemplateId` mirror backend/app/services/wa_templates.py
   `variable_count` / `GUPSHUP_ID_RE`, so the form can say "slots skip a number" before a round trip.
   The slot rule already changed once while this was being built (slots must now FIRST APPEAR in
   order), and a client looser than the server shows "Detected 2 variables" and an enabled Save for a
   body the server then refuses.

   Both sides read scripts/wa-template-cases.json:
     - this script runs every case through the REAL src/lib/api.ts (bundled on the fly with esbuild,
       which Vite already ships — not a hand-copied mirror that could drift from it);
     - backend/tests/test_wa_template_mirror.py runs the same cases through the real server functions.
   So one side changing without the other fails a check. To change a rule: change BOTH sides and the table.

   The table:  "vars": [[body, n], …]   n = the slot count, or -1 when the body is refused
               "ids":  [[value, ok], …]  ok = whether the Gupshup template id shape is accepted

     node scripts/check-wa-templates.mjs */
import { build } from "esbuild";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const cases = JSON.parse(readFileSync(join(here, "wa-template-cases.json"), "utf8"));

const bundled = await build({
  entryPoints: [join(here, "../src/lib/api.ts")],
  bundle: true, platform: "node", format: "esm", write: false, logLevel: "silent",
  // api.ts reads import.meta.env at import time; Vite fills that in, plain node has none
  define: { "import.meta.env": "{}" },
});
const out = join(tmpdir(), `wa-templates-${process.pid}.mjs`);
writeFileSync(out, bundled.outputFiles[0].text);
let m;
try { m = await import(pathToFileURL(out).href); } finally { rmSync(out); }

const failures = [];
for (const [body, n] of cases.vars) {
  const got = m.templateVars(body);
  if (got !== n) failures.push(`templateVars(${JSON.stringify(body)}) = ${got}, the table says ${n}`);
}
for (const [value, ok] of cases.ids) {
  const got = m.isGupshupTemplateId(value);
  if (got !== ok) failures.push(`isGupshupTemplateId(${JSON.stringify(value)}) = ${got}, the table says ${ok}`);
}

// a guard run over an emptied or one-sided table would pass by never saying no (or never saying yes)
const has = (rows, pick) => rows.some(pick);
if (!(has(cases.vars, ([, n]) => n >= 0) && has(cases.vars, ([, n]) => n === -1)
    && has(cases.ids, ([, ok]) => ok) && has(cases.ids, ([, ok]) => !ok))) {
  failures.push("the table must hold accepted AND refused cases for both the slot rule and the id shape");
}

if (failures.length) {
  console.error(`wa templates: ${failures.length} mismatch(es) against scripts/wa-template-cases.json`);
  for (const f of failures) console.error("  " + f);
  process.exit(1);
}
const total = cases.vars.length + cases.ids.length;
console.log(`wa templates: ok - ${total}/${total} cases (${cases.vars.length} slot rule, ${cases.ids.length} id shape)`);
