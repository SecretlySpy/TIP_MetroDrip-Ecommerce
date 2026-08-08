/**
 * Dead-selector guard.
 *
 * Exists because a responsive tier shipped referencing `.contact-form`,
 * `.developers-content` and `.empty-state__body` — none of which existed
 * anywhere in the repo. The CSS parsed, the page rendered, nothing errored, and
 * the rules were simply inert. A dead selector is worse than a missing one: in
 * review it reads as covered.
 *
 * Naive substring matching does not work here, because templates compose class
 * names at render time:
 *
 *     <div class="kpi-card{% if variant %} kpi-card--{{ variant }}{% endif %}">
 *
 * `kpi-card--volt` never appears literally, yet it is very much used. So this
 * parses `class="..."` attributes into tokens, and any token containing a
 * template expression contributes a *prefix* that marks the whole family live.
 *
 * Scope is deliberately narrow: only classes targeted **inside `@media`
 * blocks**. That is exactly where the regression happened, and it avoids
 * demanding the deletion of design-system variants (`.btn--ghost`,
 * `.waybill-border`) that were authored ahead of their first use — a different
 * judgement call, and not this guard's business.
 *
 * Usage:  node scripts/check-css-selectors.mjs
 * Exits non-zero when a responsive rule targets a class no markup can produce.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const STYLESHEETS = ["static/css/storefront.css", "static/css/console.css"];
const SOURCE_DIRS = ["templates", "static/js", "apps"];
const SOURCE_EXT = new Set([".html", ".js", ".py"]);

/**
 * Classes with no authored reference, each with a reason. Django's admin and
 * htmx both inject class names we never write ourselves; without this the guard
 * would demand we delete rules that style third-party markup.
 */
const ALLOWED_UNUSED = new Map([
  ["htmx-request", "htmx adds this during a request"],
  ["htmx-indicator", "htmx toggles this on indicators"],
  ["htmx-settling", "htmx adds this while settling"],
  ["htmx-swapping", "htmx adds this while swapping"],
  ["sr-only", "accessibility utility; must stay available even when unused"],
  ["skeleton", "applied by the htmx indicator markup at runtime"],
  // Pre-existing dead CSS, recorded rather than deleted: both were authored
  // with responsive rules but never applied to any template. Flagged in
  // ADR-P5-003; removing another author's unapplied layout is a separate call.
  ["content", "Django admin renders id=\"content\"; the `.content, #content` hedge is vestigial"],

]);

/** Django admin renders these itself; we only restyle them. */
const DJANGO_ADMIN_PREFIXES = [
  "action-checkbox", "add-related", "addlink", "aligned", "breadcrumbs", "calendarbox",
  "cancel-link", "change-list", "change-related", "changelink", "changelist", "clockbox",
  "delete-confirmation", "delete-related", "deletelink", "errorlist", "errornote", "form-row",
  "help", "helptext", "inline-group", "inline-related", "messagelist", "module", "nav-sidebar",
  "object-tools", "paginator", "related-widget-wrapper", "required", "results", "selected",
  "sortremove", "sorted", "submit-row", "tabular", "toggle-nav-sidebar", "toplinks", "viewlink",
  "vLargeTextField", "xfull", "actions",
];

function walk(dir, out = []) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    if (entry === "node_modules" || entry === "__pycache__" || entry === "migrations") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (SOURCE_EXT.has(extname(full))) out.push(full);
  }
  return out;
}

const source = SOURCE_DIRS.flatMap((d) => walk(join(ROOT, d)))
  .map((f) => readFileSync(f, "utf8"))
  .join("\n");

// Exact class tokens, plus prefixes contributed by template-composed names.
const used = new Set();
const usedPrefixes = [];

function addToken(raw) {
  const token = raw.trim();
  if (!token) return;
  const expression = token.search(/\{\{|\{%/);
  if (expression === -1) {
    used.add(token);
  } else if (expression > 0) {
    // `kpi-card--{{ variant }}` marks every `kpi-card--*` as live.
    usedPrefixes.push(token.slice(0, expression));
  }
}

// class="..." / class='...' in templates.
for (const m of source.matchAll(/class\s*=\s*["']([^"']*)["']/g)) {
  // Strip template tags first so `{% if x %}` does not split into junk tokens,
  // but keep a marker so composed names still register as prefixes.
  m[1]
    .replace(/\{%[^%]*%\}/g, " ")
    .split(/\s+/)
    .forEach(addToken);
  for (const inner of m[1].matchAll(/([\w-]+)\{\{/g)) usedPrefixes.push(inner[1]);
}
// Alpine binds classes as :class="{ 'navbar__links--open': mobileNav }" —
// a genuine usage that never appears in a plain class attribute.
for (const m of source.matchAll(/:class\s*=\s*(["'])([\s\S]*?)\1/g)) {
  for (const lit of m[2].matchAll(/['"]([\w-]+)['"]\s*:/g)) addToken(lit[1]);
}
// classList.add('x') / className = 'x' in JS.
for (const m of source.matchAll(/classList\.(?:add|remove|toggle)\(([^)]*)\)/g)) {
  for (const lit of m[1].matchAll(/["'`]([^"'`]+)["'`]/g)) lit[1].split(/\s+/).forEach(addToken);
}
for (const m of source.matchAll(/className\s*=\s*["'`]([^"'`]+)["'`]/g)) {
  m[1].split(/\s+/).forEach(addToken);
}

function isUsed(name) {
  if (used.has(name)) return true;
  if (ALLOWED_UNUSED.has(name)) return true;
  if (usedPrefixes.some((p) => p && name.startsWith(p))) return true;
  if (DJANGO_ADMIN_PREFIXES.some((p) => name === p || name.startsWith(`${p}-`))) return true;
  return false;
}

let failures = 0;
for (const sheet of STYLESHEETS) {
  const css = readFileSync(join(ROOT, sheet), "utf8");
  // Strip comments: prose naming a removed class must not read as a rule.
  const rules = css.replace(/\/\*[\s\S]*?\*\//g, "");

  // Only look inside @media blocks. Brace-match from each `@media` so nested
  // rules are captured without a full CSS parser.
  const declared = new Set();
  for (const at of [...rules.matchAll(/@media[^{]*\{/g)]) {
    let depth = 1;
    let i = at.index + at[0].length;
    const start = i;
    while (i < rules.length && depth > 0) {
      if (rules[i] === "{") depth++;
      else if (rules[i] === "}") depth--;
      i++;
    }
    const block = rules.slice(start, i - 1);
    // Selector text only — skip declaration values, where `.5rem` etc. live.
    for (const rule of block.matchAll(/([^{}]+)\{[^{}]*\}/g)) {
      for (const m of rule[1].matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) declared.add(m[1]);
    }
  }

  const dead = [...declared].filter((c) => !isUsed(c)).sort();
  if (dead.length) {
    failures += dead.length;
    console.log(
      `\nFAIL ${sheet} — ${dead.length} class(es) targeted by a responsive rule but ` +
        `reachable from no markup:`,
    );
    for (const c of dead) console.log(`  .${c}`);
  } else {
    console.log(
      `PASS ${sheet} — ${declared.size} class selector(s) inside @media blocks, all reachable`,
    );
  }
}

if (failures) {
  console.log(
    `\n${failures} dead selector(s). Use them, delete them, or add them to ALLOWED_UNUSED ` +
      `with a reason.`,
  );
}
process.exit(failures === 0 ? 0 : 1);
