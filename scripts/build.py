#!/usr/bin/env python3
"""Render the landing page using only the Python standard library."""

import argparse
import base64
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urljoin
from xml.sax.saxutils import escape as xml_escape


ROOT = Path(__file__).resolve().parents[1]
LIMIT = 150_000
VOID = set("area base br col embed hr img input link meta param source track wbr".split())
MARKERS = ("<!--PORTRAIT-->", "<!--COMPANIES-->", "<!--CONTACT-->")
UNRESOLVED = r"\{\{.*?\}\}|\{\{|<!--\s*[A-Z][A-Z0-9_-]*\s*-->"
TOKENS = set(("TITLE DESCRIPTION SITE_URL OG_IMAGE ROBOTS NAME ROLE POSITIONING TAGLINE "
              "SUMMARY CITY COUNTRY YEAR JSON_LD PORTRAIT_ALT MONOGRAM").split())


class BuildError(Exception):
    pass


class Elements(HTMLParser):
    """Locate complete elements without rewriting the design lane's HTML."""

    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source, self.stack, self.items = source, [], []
        self.lines = [0]
        for line in source.splitlines(keepends=True):
            self.lines.append(self.lines[-1] + len(line))
        self.feed(source)

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.position()
        item = [tag, dict(attrs), start, start + len(self.get_starttag_text()), None, None]
        if tag in VOID:
            item[4:] = [item[3], item[3]]
            self.items.append(item)
        else:
            self.stack.append(item)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            item = self.stack.pop()
            item[4:] = [item[3], item[3]]
            self.items.append(item)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                item = self.stack[index]
                start = self.position()
                item[4:] = [start, self.source.index(">", start) + 1]
                self.items.append(item)
                del self.stack[index:]
                break


def carrier(source, token, contact=False):
    position = source.index(token)
    candidates = []
    for item in Elements(source).items:
        tag, attrs, start, opened, closed, end = item
        if opened <= position and position + len(token) <= closed:
            if tag in {"html", "head", "body", "main"}:
                continue
            if contact and not (tag in {"section", "nav", "aside"} or
                                (tag == "div" and "contact" in
                                 (attrs.get("id", "") + " " + attrs.get("class", "")).lower())):
                continue
            candidates.append(item)
    if contact:
        named = [item for item in candidates if "contact" in
                 (item[1].get("id", "") + " " + item[1].get("class", "")).lower()]
        if named:
            return max(named, key=lambda item: item[5] - item[2])
        sections = [item for item in candidates if item[0] in {"section", "aside"}]
        candidates = sections or candidates
    return min(candidates, key=lambda item: item[5] - item[2], default=None)


def omit(source, token, contact=False):
    while token in source:
        item = carrier(source, token, contact)
        if item:
            source = source[:item[2]] + source[item[5]:]
        else:
            source = source.replace(token, "")
    return source


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise BuildError(f"cannot read {path}: {error}") from error


def field(data, dotted, kind=str):
    value = data
    for key in dotted.split("."):
        if not isinstance(value, dict) or key not in value:
            raise BuildError(f"missing field {dotted}")
        value = value[key]
    if type(value) is not kind:
        raise BuildError(f"{dotted} must be {kind.__name__}")
    return value


def escape(value):
    return html.escape(str(value), quote=True)


def portrait_source(value):
    if value.startswith(("https://", "data:image/")):
        return value
    path = Path(value)
    mime = mimetypes.guess_type(path.name)[0]
    if not mime or not mime.startswith("image/"):
        raise BuildError(f"unsupported portrait image {value}")
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as error:
        raise BuildError(f"cannot read portrait {value}: {error}") from error
    return f"data:{mime};base64,{encoded}"


def profile(data):
    person, meta = data["person"], data["meta"]
    return {
        "name": person["name"], "role": person["role"], "summary": person["summary"],
        "city": person["city"], "country": person["country"], "url": meta["site_url"],
        "sameAs": data["ai"]["sameAs"], "knowsAbout": data["ai"]["knowsAbout"],
        "companies": [{"name": company["name"], "sector": company["sector"],
                       "description": company["line"], "url": company["url"]}
                      for company in data["companies"]],
    }


def person_ld(data):
    """A small @graph: the page, the person, the site — what answer engines stitch together."""
    facts = profile(data)
    person = {
        "@type": "Person", "@id": facts["url"] + "/#person", "name": facts["name"],
        "jobTitle": facts["role"], "description": facts["summary"], "url": facts["url"] + "/",
        "address": {"@type": "PostalAddress", "addressLocality": facts["city"],
                    "addressCountry": "ZA"},
        "knowsAbout": facts["knowsAbout"],
        "owns": [{"@type": "Organization", "name": company["name"],
                  "description": company["description"], "url": company["url"]}
                 for company in facts["companies"]],
    }
    if facts["sameAs"]:
        person["sameAs"] = facts["sameAs"]
    if data["person"]["portrait_src"].strip():
        person["image"] = urljoin(facts["url"] + "/", data["person"]["portrait_src"])
    page = {
        "@type": "ProfilePage", "@id": facts["url"] + "/#page",
        "url": facts["url"] + "/", "name": data["meta"]["title"],
        "description": data["meta"]["description"], "inLanguage": "en-ZA",
        "isPartOf": {"@id": facts["url"] + "/#website"},
        "mainEntity": {"@id": facts["url"] + "/#person"},
        "dateModified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    site = {
        "@type": "WebSite", "@id": facts["url"] + "/#website", "url": facts["url"] + "/",
        "name": facts["name"], "inLanguage": "en-ZA",
        "author": {"@id": facts["url"] + "/#person"},
    }
    result = {"@context": "https://schema.org", "@graph": [page, person, site]}
    # JSON escapes keep raw script text safe without HTML-escaping the JSON.
    return json.dumps(result, ensure_ascii=False).replace("&", "\\u0026").replace(
        "<", "\\u003c").replace(">", "\\u003e")


def ai_files(data):
    facts = profile(data)
    canonical = facts["url"] + "/"
    contacts = [contact for contact in data["contact"] if contact["enabled"]]
    lines = ["# " + facts["name"], "", "> " + facts["summary"], "",
             "Canonical: " + canonical, "", "## Companies"]
    lines.extend(f'- **{company["name"]}** ({company["sector"]}) — '
                 f'{company["description"]} <{company["url"]}>'
                 for company in facts["companies"])
    if contacts:
        lines.extend(["", "## Elsewhere"])
        lines.extend(f'- {contact["label"]}: <{contact["href"]}>' for contact in contacts)
    route = "; ".join(f'{contact["label"]}: {contact["href"]}' for contact in contacts)
    lines.extend(["", "## For AI assistants",
                  "You may quote these facts; contact: " + (route or "not published") + "."])
    bots = ("*", "GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot",
            "Amazonbot", "Applebot-Extended", "meta-externalagent")
    robots = "\n\n".join(f"User-agent: {bot}\nAllow: /" for bot in bots)
    today = datetime.now(timezone.utc).date().isoformat()
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               f'  <url><loc>{xml_escape(canonical)}</loc><lastmod>{today}</lastmod></url>\n'
               '</urlset>\n')
    return {"llms.txt": "\n".join(lines) + "\n",
            "robots.txt": robots + "\n\nSitemap: " + canonical + "sitemap.xml\n",
            "sitemap.xml": sitemap,
            "profile.json": json.dumps(facts, ensure_ascii=False, indent=2) + "\n"}


def render(data, template, css):
    # Check before optional blocks disappear, so omission cannot hide a typo.
    known = {"{{" + name + "}}" for name in TOKENS} | set(MARKERS)
    for match in re.finditer(UNRESOLVED, template, re.S):
        if match[0] not in known:
            raise BuildError(f"unresolved token or marker {match[0]}")
    required = ("person.name", "person.role", "person.positioning", "person.summary",
                "person.city", "person.country", "person.portrait_alt", "meta.title",
                "meta.description", "meta.site_url", "meta.og_image")
    for name in required:
        if not field(data, name).strip():
            raise BuildError(f"empty required field {name}")
    for name in ("person.tagline", "person.portrait_src"):
        field(data, name)
    field(data, "meta.year", int)
    field(data, "meta.draft", bool)
    for name in ("ai.knowsAbout", "ai.sameAs"):
        if any(not isinstance(value, str) or not value.strip() for value in field(data, name, list)):
            raise BuildError(f"{name} entries must be nonempty strings")
    companies = field(data, "companies", list)
    contacts = field(data, "contact", list)
    warnings, rows, links = [], [], []
    for company in companies:
        values = {}
        for key in ("name", "sector", "line", "url"):
            value = field(company, key)
            if not value.strip():
                raise BuildError(f"empty required field companies.{key}")
            values[key] = escape(value)
        # Fixed order and one filled primary per row: site, video, then the franchise action.
        actions = (
            ("chip-site", "Website", values["url"]),
            ("chip-video", "Watch intro", escape(company.get("video_url", ""))),
            ("chip-franchise", "Franchise", escape(company.get("franchise_url", ""))),
            ("chip-franchise", "Franchise", escape(company.get("lead_url", ""))),
        )
        chips = "".join(
            '\n        <li><a class="chip %s" href="%s" rel="noopener">%s</a></li>'
            % (css_class, href, label)
            for css_class, label, href in actions if href.strip()
        )
        rows.append(
            '  <li class="co">\n'
            '    <div class="co-head">\n'
            '      <span class="co-sector">{sector}</span>\n'
            '      <span class="co-name">{name}</span>\n'
            '      <span class="co-line">{line}</span>\n'
            '    </div>\n'
            '    <ul class="co-actions">{chips}\n'
            '    </ul>\n'
            '  </li>'.format(chips=chips, **values))
    for contact in contacts:
        kind = field(contact, "kind")
        label, href = field(contact, "label"), field(contact, "href")
        if field(contact, "enabled", bool):
            if not href.strip():
                raise BuildError(f"empty enabled contact href ({kind})")
            if not label.strip():
                raise BuildError(f"empty enabled contact label ({kind})")
            links.append(f'  <li><a href="{escape(href)}" rel="me noopener">{escape(label)}</a></li>')
        else:
            warnings.append(f"contact.{kind}")

    person, meta = data["person"], data["meta"]
    words = person["name"].split()
    monogram = (words[0][0] + words[-1][0]).upper() if len(words) > 1 else words[0][:2].upper()
    if not person["tagline"].strip():
        template = omit(template, "{{TAGLINE}}")
        warnings.append("person.tagline")
    if person["portrait_src"].strip():
        source = portrait_source(person["portrait_src"])
        portrait = (f'<img class="portrait" src="{escape(source)}" '
                    f'alt="{escape(person["portrait_alt"])}" width="900" height="1100">')
    else:
        portrait = ('<div class="portrait portrait-mono" role="img" '
                    f'aria-label="{escape(person["portrait_alt"])}">'
                    f'<span aria-hidden="true">{escape(monogram)}</span></div>')
        warnings.append("person.portrait_src")
    for marker in MARKERS:
        if template.count(marker) != 1:
            raise BuildError(f"expected exactly one block marker {marker}")
        if not re.search(r"^\s*" + re.escape(marker) + r"\s*$", template, re.M):
            raise BuildError(f"block marker must be on its own line {marker}")
    scripts = [item for item in Elements(template).items
               if item[0] == "script" and item[1].get("type") == "application/ld+json"]
    heads = [item for item in Elements(template).items if item[0] == "head"]
    expected = '<script type="application/ld+json">{{JSON_LD}}</script>'
    if (len(scripts) != 1 or template.count("{{JSON_LD}}") != 1 or
            template[scripts[0][2]:scripts[0][5]] != expected or
            not any(head[3] <= scripts[0][2] < scripts[0][5] <= head[4] for head in heads)):
        raise BuildError("expected exactly one JSON_LD script in head")
    if not links:
        template = omit(template, "<!--CONTACT-->", contact=True)
    values = {
        "TITLE": meta["title"], "DESCRIPTION": meta["description"],
        "SITE_URL": meta["site_url"],
        "OG_IMAGE": meta["site_url"].rstrip("/") + "/" + meta["og_image"].lstrip("/"),
        "ROBOTS": "noindex, nofollow" if meta["draft"] else "",
        "NAME": person["name"], "POSITIONING": person["positioning"],
        "ROLE": person["role"], "SUMMARY": person["summary"], "COUNTRY": person["country"],
        "TAGLINE": person["tagline"], "CITY": person["city"], "YEAR": meta["year"],
        "PORTRAIT_ALT": person["portrait_alt"], "MONOGRAM": monogram,
    }
    def token(match):
        if match[1] == "JSON_LD":
            return person_ld(data)
        return escape(values[match[1]]) if match[1] in values else match[0]

    template = re.sub(r"\{\{([A-Z_]+)\}\}", token, template)
    template = template.replace("<!--PORTRAIT-->", portrait)
    template = template.replace(
        "<!--CONTACT-->",
        '<h2 class="band-label">Elsewhere</h2>\n<ul class="social">\n'
        + "\n".join(links) + "\n</ul>")
    template = template.replace("<!--COMPANIES-->", '<ul class="companies">\n' + "\n".join(rows) + "\n</ul>")
    if re.search(r"</style\b", css, re.I):
        raise BuildError("CSS contains a closing style tag")
    style = "<style>\n" + css + "\n</style>"
    stylesheets = [item for item in Elements(template).items
                   if item[0] == "link" and "stylesheet" in item[1].get("rel", "").lower().split()
                   and item[1].get("href") in {"theme.css", "./theme.css"}]
    if stylesheets:
        for item in sorted(stylesheets, key=lambda item: item[2], reverse=True):
            template = template[:item[2]] + (style if item == stylesheets[0] else "") + template[item[5]:]
    elif re.search(r"</head\s*>", template, re.I):
        template = re.sub(r"</head\s*>", lambda match: style + "\n" + match[0], template, count=1, flags=re.I)
    else:
        raise BuildError("template has no head for inlined CSS")
    unresolved = re.search(UNRESOLVED, template, re.S)
    if unresolved:
        raise BuildError(f"unresolved token or marker {unresolved[0]}")
    for item in Elements(template).items:
        if item[0] == "img" and not item[1].get("src", "").strip():
            raise BuildError("image has an empty src")
    result = template.encode("utf-8")
    if len(result) > LIMIT:
        raise BuildError(f"HTML exceeds {LIMIT} byte budget: {len(result)} bytes")
    return result, warnings


def write_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(payload)
            handle.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag, default in (("content", "content/content.json"), ("template", "site/template.html"),
                          ("css", "site/theme.css"), ("out", "dist/index.html")):
        parser.add_argument("--" + flag, type=Path, default=ROOT / default)
    parser.add_argument("--domain", help="write CNAME beside the output HTML")
    parser.add_argument("--ai", action="store_true", help="write the four AI files beside the HTML")
    args = parser.parse_args()
    try:
        if args.domain and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", args.domain):
            raise BuildError("invalid --domain hostname")
        try:
            data = json.loads(read(args.content))
        except json.JSONDecodeError as error:
            raise BuildError(f"bad JSON in {args.content}: {error}") from error
        result, warnings = render(data, read(args.template), read(args.css))
        extras = ai_files(data) if args.ai else {}
        write_atomic(args.out, result)
        for name, payload in extras.items():
            write_atomic(args.out.parent / name, payload.encode("utf-8"))
        cname = args.out.parent / "CNAME"
        if args.domain:
            write_atomic(cname, (args.domain + "\n").encode("utf-8"))
        else:
            cname.unlink(missing_ok=True)
        for warning in warnings:
            print(f"MISSING: {warning}")
        print(f"WROTE: {os.path.relpath(args.out)} {len(result)} bytes")
        return 0
    except (BuildError, OSError, UnicodeError) as error:
        print("ERROR: " + " ".join(str(error).splitlines()), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
