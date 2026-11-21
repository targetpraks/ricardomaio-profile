# ricardomaio.co.za — personal + business landing page

The single link in every social bio: who Ricardo Maio is, the four companies he runs, and how to
reach him. One static page, no JavaScript, no frameworks, no external fonts. Content is data
(`content/content.json`); the page is generated.

Built by three lanes from `CONTRACT.md` — design (Claude Code, opus), build pipeline (Codex,
gpt-6.1-sol), independent verification (OpenCode, kimi-k3.1-pro) — then integrated and verified.

## Build

Python 3, standard library only. Run from this directory:

```bash
python3 scripts/build.py          # content + site/template.html + site/theme.css -> dist/index.html
bash scripts/share-card.sh        # assets/share-card.html -> dist/og.png (1200x630)
python3 scripts/check.py          # independent assertions on dist/index.html
```

Flags: `--content PATH`, `--template PATH`, `--css PATH`, `--out PATH`, `--domain HOSTNAME`,
`-h`/`--help`. `--domain ricardomaio.co.za` writes a `CNAME` beside the output HTML — only do that
once the domain actually resolves, or GitHub Pages will redirect and 404. Without `--domain`, a stale
generated CNAME is removed.

All build errors print one reason and exit 2. Output is validated before an atomic replacement, so an
unsuccessful render preserves the earlier HTML. Byte budget: 150,000 bytes.

`scripts/check.py` fails the build on a leftover token, on `Codeblaze` or `Titan Electrical` appearing
anywhere, on a company count or URL that does not match the content file, on any non-HTTPS link, on a
missing `og:`/`twitter:` tag, and on any reference to a local file other than a fragment.

## How the pieces fit

- `content/content.json` — all copy and links. **The only place text lives.** Nothing is hard-coded.
- `site/template.html` — page markup with `{{TOKENS}}` plus the `<!--COMPANIES-->` and `<!--CONTACT-->`
  block markers. Tokens: `TITLE DESCRIPTION SITE_URL OG_IMAGE ROBOTS NAME POSITIONING TAGLINE CITY
  YEAR PORTRAIT_ALT MONOGRAM`. `theme.css` is inlined by the build and its `<link>` removed.
- `site/theme.css` — the stylesheet. Styles `ul.companies > li > a` with `.co-name` / `.co-line` and
  draws the arrow itself via `::after`; styles `.contact-slot ul` as an inline row.
- `assets/share-card.html` — the 1200×630 card, screenshotted by `scripts/share-card.sh`.
- `scripts/build.py` — the renderer. Companies become `<ul class="companies"><li><a>…`; contacts
  become `<ul class="contact"><li><a>…`. Both wrappers are ours, not the template's.
- `scripts/check.py` — the verification lane's checker. It never imports or trusts `build.py`.

Empty states are the live states, not edge cases: with no portrait the page shows an `RM` monogram
square, and with every contact entry disabled the whole contact block is removed (build prints
`MISSING: contact.email` etc.).

## AI layer

`python3 scripts/build.py --ai` also writes, beside the HTML: `llms.txt` (a plain-text summary any AI agent can
read — who he is, the five companies with URLs, the contact route), `robots.txt` (explicit `Allow: /` for
GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot, Amazonbot, Applebot-Extended and meta-externalagent,
plus the sitemap), `sitemap.xml`, and `profile.json` (machine-readable person + companies). The page itself
carries one `Person` JSON-LD object with `owns` listing all five companies, and `person.summary` as real text
so answer engines have a sentence to quote.

## Deploy

`.github/workflows/pages.yml` builds on every push to `main`, runs the checker, and publishes `dist/`
to GitHub Pages. `assets/og.png` is committed because the share image needs a real Chrome, which the
runner does not have.

Live preview: https://targetpraks.github.io/ricardomaio-profile/

Custom domain (`ricardomaio.co.za`): register it, add a `CNAME` record to `targetpraks.github.io`,
then build with `--domain ricardomaio.co.za` and set the same host in the repository's Pages settings.
`meta.draft: true` keeps the page `noindex, nofollow` until the copy is approved — set it to `false`
in `content/content.json` to let the page be indexed.

## Status

Copy, four company links and layout are built and verified. Still open: a portrait photo, the
contact handles (email, WhatsApp, LinkedIn, Instagram — all disabled until supplied), the domain
purchase, and approval of the positioning line.
