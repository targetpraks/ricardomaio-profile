# CONTRACT — ricardomaio.co.za landing page

Three lanes build this page in parallel. This file is the interface between them. Do not change it;
build to it. If the contract is wrong or impossible, say so in your report and build the closest correct thing.

## What is being built

One static page: **Ricardo Maio's personal + business landing page**. It is the single link in every
social bio. Not a blog, not a store, no forms, no JavaScript beyond nothing at all, no external fonts,
no external scripts, no frameworks. One self-contained HTML file plus one 1200×630 share image.

Content is **data**, never markup: `content/content.json` is the only place copy lives.

## Files and who owns them

| Path | Owner lane | Purpose |
|---|---|---|
| `content/content.json` | parent (read-only to you) | all copy and links; the only source of text |
| `site/template.html` | **A — design** | the whole page markup, with `{{TOKENS}}` and two block markers |
| `site/theme.css` | **A — design** | the whole stylesheet |
| `assets/share-card.html` | **A — design** | fixed 1200×630 card, self-contained inline CSS |
| `scripts/build.py` | **B — build** | render `dist/index.html` from content + template + css |
| `scripts/share-card.sh` | **B — build** | Chrome headless screenshot of the card → `dist/og.png` |
| `scripts/check.py` | **C — verify** | independent assertions on `dist/index.html`, standalone |
| `dist/` | generated | never hand-edited |

## content.json schema (authoritative)

```json
{
  "person": {
    "name": "string",
    "positioning": "string — one plain sentence, shown large",
    "tagline": "string — his own voice, shown small; may be empty",
    "city": "string",
    "portrait_src": "string — may be EMPTY, see below",
    "portrait_alt": "string"
  },
  "companies": [
    { "name": "string", "line": "string", "url": "https://…" }
  ],
  "contact": [
    { "kind": "email|whatsapp|linkedin|instagram|x", "label": "string", "href": "string", "enabled": true }
  ],
  "meta": {
    "title": "string", "description": "string", "site_url": "https://…",
    "og_image": "og.png", "year": 2026, "draft": true
  }
}
```

Rules the renderer must honour:

- `person.portrait_src` **may be an empty string**. The template must render a monogram block in its place
  — a square carrying the initials `RM` — and must not emit an `<img>` with an empty `src`.
- `contact` entries with `enabled: false` are **omitted entirely** from the output. If every contact entry is
  disabled, the whole contact block is omitted (no empty heading, no placeholder text). `build.py` prints a
  warning listing which contact kinds are missing; it does not fail on them.
- `companies` must render as exactly as many rows as the array has, in array order.
- `meta.draft: true` → `<meta name="robots" content="noindex, nofollow">`.

## Template tokens

`site/template.html` is a complete `<!doctype html>` document. Available tokens, resolved by `build.py`
with plain string replacement (exact spelling, no filters):

| Token | From |
|---|---|
| `{{TITLE}}` | `meta.title` |
| `{{DESCRIPTION}}` | `meta.description` |
| `{{SITE_URL}}` | `meta.site_url` |
| `{{OG_IMAGE}}` | `meta.site_url` + `/` + `meta.og_image` |
| `{{ROBOTS}}` | `noindex, nofollow` when draft, else empty string |
| `{{NAME}}` | `person.name` |
| `{{POSITIONING}}` | `person.positioning` |
| `{{TAGLINE}}` | `person.tagline` (the element carrying it is omitted when empty) |
| `{{CITY}}` | `person.city` |
| `{{YEAR}}` | `meta.year` |
| `{{PORTRAIT_ALT}}` | `person.portrait_alt` |
| `{{MONOGRAM}}` | `RM` |

Two block markers, each on its own line, replaced by generated markup:

- `<!--COMPANIES-->` → the companies list, one row per entry
- `<!--CONTACT-->` → the contact list; omitted block if no entries are enabled

`build.py` must **fail loudly with exit code 2** if any `{{TOKEN}}` remains unresolved, if a
`<!--MARKER-->` remains unreplaced, or if any of `person.name`, `person.positioning`,
`meta.title`, `meta.description` is empty. It prints `MISSING: <field>` lines for warnings
(portrait, tagline, disabled contact kinds) and `WROTE: dist/index.html <bytes> bytes`.

## Output

- `dist/index.html` — **single self-contained file**: `theme.css` is inlined into a `<style>` block and the
  `<link rel="stylesheet">` that pointed at it is removed. No other local files are referenced.
- `dist/og.png` — 1200×630, produced from `assets/share-card.html` via
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars
  --window-size=1200,630 --screenshot=dist/og.png file://…/assets/share-card.html`
- `dist/index.html` must be at or under **150 KB** including inlined CSS.
- `dist/CNAME` is **only** written when `build.py` is called with `--domain ricardomaio.co.za`. Default: no CNAME.

## Design constraints (lane A)

- Palette: ink `#12202E`, navy `#0B2239`, accent `#B4451F`, paper `#FBF8F3`, line `#D9D2C6`, muted `#5C6773`.
- Type: system serif for display (`Georgia, "Iowan Old Style", "Times New Roman", serif`), system sans for
  body (`-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`). No webfonts.
- One column, `max-width: 720px`, centred, generous whitespace. Editorial and personal, not a SaaS landing page.
- Hero: name, positioning line, tagline, city. Portrait on the right at ≥760px, above the name on phones.
- Companies: large text rows, name + one line + arrow, whole row is the link, minimum 44px tap height.
- Contact: a single horizontal row of plain text links.
- Phone-first: at 390px there is **zero horizontal scroll** and no text under 15px.
- Accessibility: `:focus-visible` outlines, `prefers-reduced-motion` respected, contrast ≥ 4.5:1, `lang="en"`.

## Independent verification (lane C)

`scripts/check.py` takes `dist/index.html` (path as argv, default `dist/index.html`) and, using only the
Python standard library, asserts and prints one line per check, `PASS`/`FAIL`, then a final
`RESULT: PASS` or `RESULT: FAIL` with a non-zero exit on failure:

1. no `{{` or `<!--COMPANIES-->` remains;
2. the exact strings `Codeblaze` and `Titan Electrical` appear **nowhere**, case-insensitive;
3. the company rows number exactly as many as `content/content.json` has entries, and each company `url`
   appears as an `href`;
4. every `href` either starts with `https://` or is an in-page anchor `#…`; no `http://`, no `javascript:`;
5. `<meta name="viewport">`, a single `<h1>`, `lang="en"`, `og:title`, `og:description`, `og:image`,
   `twitter:card` are all present;
6. the file is at or under 150 KB, and no `src=` or `href=` points at a local file other than `#`;
7. prints `ANCHORS <n>` with the count of external anchors.

It must **not** import `build.py` and must not trust `build.py`'s own output messages.

## Definition of done for the whole build

`python3 scripts/build.py && bash scripts/share-card.sh && python3 scripts/check.py` all exit 0, and
`dist/index.html` renders at 390px with no horizontal scroll.
