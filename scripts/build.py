#!/usr/bin/env python3
"""Render the landing page using only the Python standard library."""

import argparse
import base64
import html
from html.parser import HTMLParser
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
LIMIT = 150_000
VOID = set("area base br col embed hr img input link meta param source track wbr".split())


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


def render(data, template, css):
    required = ("person.name", "person.positioning", "meta.title", "meta.description")
    for name in required:
        if not field(data, name).strip():
            raise BuildError(f"empty required field {name}")
    for name in ("person.tagline", "person.city", "person.portrait_src",
                 "person.portrait_alt", "meta.site_url", "meta.og_image"):
        field(data, name)
    field(data, "meta.year", int)
    field(data, "meta.draft", bool)
    companies = field(data, "companies", list)
    contacts = field(data, "contact", list)
    warnings, rows, links = [], [], []
    for company in companies:
        values = {key: escape(field(company, key)) for key in ("name", "line", "url")}
        # Markup contract: the design lane styles `ul.companies > li > a` with
        # `.co-name` / `.co-line` and draws the arrow itself via ::after.
        rows.append('<li><a href="{url}"><span class="co-name">{name}</span>'
                    '<span class="co-line">{line}</span></a></li>'.format(**values))
    for contact in contacts:
        kind = field(contact, "kind")
        label, href = field(contact, "label"), field(contact, "href")
        if field(contact, "enabled", bool):
            if not href.strip():
                raise BuildError(f"empty enabled contact href ({kind})")
            links.append(f'<li><a href="{escape(href)}">{escape(label)}</a></li>')
        else:
            warnings.append(f"contact.{kind}")

    person, meta = data["person"], data["meta"]
    words = person["name"].split()
    monogram = (words[0][0] + words[-1][0]).upper() if len(words) > 1 else words[0][:2].upper()
    if not person["tagline"].strip():
        template = omit(template, "{{TAGLINE}}")
        warnings.append("person.tagline")
    image = None
    if person["portrait_src"].strip():
        source = portrait_source(person["portrait_src"])
        if "{{MONOGRAM}}" not in template or not carrier(template, "{{MONOGRAM}}"):
            raise BuildError("portrait requires an element containing {{MONOGRAM}}")
        image = f'<img src="{escape(source)}" alt="{escape(person["portrait_alt"])}">'
    else:
        warnings.append("person.portrait_src")
    for marker in ("<!--COMPANIES-->", "<!--CONTACT-->"):
        if template.count(marker) != 1:
            raise BuildError(f"expected exactly one block marker {marker}")
    if not links:
        template = omit(template, "<!--CONTACT-->", contact=True)
    values = {
        "TITLE": meta["title"], "DESCRIPTION": meta["description"],
        "SITE_URL": meta["site_url"],
        "OG_IMAGE": meta["site_url"].rstrip("/") + "/" + meta["og_image"].lstrip("/"),
        "ROBOTS": "noindex, nofollow" if meta["draft"] else "",
        "NAME": person["name"], "POSITIONING": person["positioning"],
        "TAGLINE": person["tagline"], "CITY": person["city"], "YEAR": meta["year"],
        "PORTRAIT_ALT": person["portrait_alt"], "MONOGRAM": monogram,
    }
    def token(match):
        if match[1] == "MONOGRAM" and image:
            return image
        return escape(values[match[1]]) if match[1] in values else match[0]

    template = re.sub(r"\{\{([A-Z_]+)\}\}", token, template)
    template = template.replace("<!--CONTACT-->", '<ul class="contact">' + "\n".join(links) + "</ul>")
    template = template.replace("<!--COMPANIES-->", '<ul class="companies">' + "\n".join(rows) + "</ul>")
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
    unresolved = re.search(r"\{\{.*?\}\}|\{\{|<!--\s*[A-Z][A-Z0-9_-]*\s*-->", template, re.S)
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
    args = parser.parse_args()
    try:
        if args.domain and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", args.domain):
            raise BuildError("invalid --domain hostname")
        try:
            data = json.loads(read(args.content))
        except json.JSONDecodeError as error:
            raise BuildError(f"bad JSON in {args.content}: {error}") from error
        result, warnings = render(data, read(args.template), read(args.css))
        write_atomic(args.out, result)
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
