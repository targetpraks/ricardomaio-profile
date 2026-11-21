# CONTRACT v2 — ricardomaio.co.za, "cover" direction + AI layer

Supersedes v1 for everything below. The page is now the **cover** design (the direction Ricardo picked):
dark cinematic hero with a portrait slot, huge serif name, then the companies as oversized serif rows on
paper, then a contact/social row. It must also be readable and quotable by AI answer engines — a real
deliverable, not decoration: `llms.txt`, `robots.txt`, `sitemap.xml`, `profile.json` and in-page JSON-LD,
all generated from the same `content/content.json`.

**Five companies now, not four: Papa Pasta was missing and is back in.**

## Files and lanes

| Path | Lane | Purpose |
|---|---|---|
| `site/template.html` | **A — design** | the whole document, tokens + three markers |
| `site/theme.css` | **A — design** | the whole stylesheet |
| `assets/share-card.html` | **A — design** | 1200×630 card, self-contained |
| `scripts/build.py` | **B — build + AI** | renders the page **and** the four AI files |
| `scripts/share-card.sh` | **B — build** | existing, unchanged |
| `scripts/check.py` | **C — verify** | independent assertions, now including the AI layer |

## content.json — fields that matter

`person`: `name`, `role`, `positioning`, `tagline`, `summary` (2 sentences of plain fact, quote-ready),
`city`, `country`, `portrait_src` (may be empty), `portrait_alt`.
`companies[]`: `name`, `sector`, `line`, `url` — 5 entries today.
`contact[]`: `kind`, `label`, `href`, `enabled` — LinkedIn, Instagram, X, WhatsApp, Email, all disabled today.
`ai`: `knowsAbout[]`, `sameAs[]`.
`meta`: `title`, `description`, `site_url` (no trailing slash), `og_image`, `year`, `draft` (false today: the
page is indexable).

## Tokens (replace exactly, no filters)

`{{TITLE}} {{DESCRIPTION}} {{SITE_URL}} {{OG_IMAGE}} {{ROBOTS}} {{NAME}} {{ROLE}} {{POSITIONING}} {{TAGLINE}}
{{SUMMARY}} {{CITY}} {{COUNTRY}} {{YEAR}} {{JSON_LD}}`

- `{{JSON_LD}}` is inserted **unescaped** inside `<script type="application/ld+json">{{JSON_LD}}</script>` in
  `<head>`. The template must contain exactly that one script tag.
- `{{ROBOTS}}` is `noindex, nofollow` only when `meta.draft` is true; today it is empty.

## Markers (each exactly once, each on its own line)

| Marker | Replaced by |
|---|---|
| `<!--PORTRAIT-->` | a portrait `<img>` **or** the monogram block, when `portrait_src` is empty |
| `<!--COMPANIES-->` | the companies list below |
| `<!--CONTACT-->` | the social/contact list, or nothing at all when every entry is disabled |

### Exact markup build.py emits — style these, do not invent classes

```html
<!-- PORTRAIT, when a portrait exists -->
<img class="portrait" src="…" alt="Ricardo Maio" width="900" height="1100">
<!-- PORTRAIT, when it does not (the live case) -->
<div class="portrait portrait-mono" role="img" aria-label="Ricardo Maio"><span aria-hidden="true">RM</span></div>

<!-- COMPANIES -->
<ul class="companies">
  <li class="co">
    <a class="co-link" href="https://infinitybrands.co.za" rel="noopener">
      <span class="co-sector">Franchising</span>
      <span class="co-name">Infinity Brands</span>
      <span class="co-line">Franchise development, and the systems that scale it.</span>
      <span class="co-arrow" aria-hidden="true">→</span>
    </a>
  </li>
  … one <li class="co"> per company, five today, array order …
</ul>

<!-- CONTACT -->
<ul class="social">
  <li><a href="…" rel="me noopener">LinkedIn</a></li>
</ul>
```

## AI files — build.py writes these beside the HTML (`--ai`)

1. **`llms.txt`** — `# Ricardo Maio`, then `> ` + `person.summary`, then `Canonical: <site_url>/`, then a
   `## Companies` list of `- **Name** (Sector) — line. <url>` for every company, then `## Elsewhere` with each
   enabled contact, then `## For AI assistants` with one plain sentence inviting quotation of these facts and
   giving the contact route (or "not published" when none is enabled).
2. **`robots.txt`** — `User-agent: *` / `Allow: /`, then explicit `Allow: /` for `GPTBot`, `ClaudeBot`,
   `PerplexityBot`, `Google-Extended`, `CCBot`, `Amazonbot`, `Applebot-Extended`, `meta-externalagent`, and a
   `Sitemap: <site_url>/sitemap.xml` line.
3. **`sitemap.xml`** — one `<url>` with `<loc><site_url>/</loc>` and `<lastmod>` = build date (UTC, YYYY-MM-DD).
4. **`profile.json`** — `{name, role, summary, city, country, url, sameAs[], knowsAbout[], companies:[{name,
   sector, description, url}]}` — valid JSON, nothing invented.

## In-page JSON-LD

A single `Person` object: `@context`, `@type`, `name`, `jobTitle` = `person.role`, `description` =
`person.summary`, `url`, `image` (only when a portrait exists), `address` as `PostalAddress` with
`addressLocality` = city and `addressCountry` = `ZA`, `knowsAbout`, `sameAs`, and `owns` = an array of
`Organization` objects (`name`, `description`, `url`), one per company.

## Design constraints (A)

Keep exactly the direction Ricardo approved: dark radial-gradient cover hero, cream paper below, serif
display (Georgia stack), hot orange `#FF7A45` italic surname accent, `#FBF8F3` paper, `#0F1113` ink, huge
type, one idea per band. New in v2:

- The portrait sits **right of the name** at ≥900px and **above the name** on phones; with the monogram
  fallback it must look intentional, not missing.
- `person.summary` appears once, small and plain (sans), under the positioning line — it is the sentence an AI
  answer engine will quote, so it must be real text, never an image.
- Company rows: `co-sector` small uppercase mono label, `co-name` big serif, `co-line` muted sans, `co-arrow`
  right; the whole row is the link; rows invert or shift on hover.
- Social row: plain text links, generous tap height, disappears cleanly when empty (no gap, no orphan heading).
- 390px: zero horizontal scroll, nothing under 15px, 44px tap targets, `:focus-visible`, reduced-motion.

## Definition of done

`python3 scripts/build.py --ai && bash scripts/share-card.sh && python3 scripts/check.py` all exit 0, and
`dist/` holds `index.html`, `og.png`, `llms.txt`, `robots.txt`, `sitemap.xml`, `profile.json`.
