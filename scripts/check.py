#!/usr/bin/env python3
"""Independently check the rendered landing page against CONTRACT.md."""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 150 * 1024
FORBIDDEN_STRINGS = ("Codeblaze", "Titan Electrical")
REQUIRED_META = ("og:title", "og:description", "og:image", "twitter:card")


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []
        self.references = []
        self.h1_count = 0
        self.html_lang = None
        self.meta_names = set()
        self.meta_properties = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)

        if tag == "html":
            self.html_lang = attributes.get("lang")
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "meta":
            name = attributes.get("name")
            property_name = attributes.get("property")
            if name is not None:
                self.meta_names.add(name)
            if property_name is not None:
                self.meta_properties.add(property_name)

        for attribute in ("href", "src"):
            if attribute not in attributes:
                continue
            value = attributes[attribute]
            value = "" if value is None else value
            self.references.append((tag, attribute, value))
            if attribute == "href":
                self.hrefs.append((tag, value))


def is_local_reference(value):
    if value.startswith("#"):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return True
    return not parsed.scheme and not parsed.netloc and not value.startswith("//")


def quoted(values, limit=5):
    shown = ", ".join(repr(value) for value in values[:limit])
    if len(values) > limit:
        shown += f", ... ({len(values) - limit} more)"
    return shown


def main():
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/index.html")
    root = Path(__file__).resolve().parent.parent

    try:
        html_bytes = html_path.read_bytes()
        content = json.loads((root / "content" / "content.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL input: {error}")
        print("RESULT: FAIL")
        return 1

    html = html_bytes.decode("utf-8", errors="replace")
    parser = DocumentParser()
    parser.feed(html)
    parser.close()

    results = []

    def report(number, name, passed, evidence):
        results.append(passed)
        print(f"{'PASS' if passed else 'FAIL'} {number}. {name}: {evidence}")

    unresolved = [
        match.group(0)
        for match in re.finditer(r"\{\{[^{}]*\}\}|\{\{|<!--COMPANIES-->", html)
    ]
    report(
        1,
        "no unresolved tokens or companies marker",
        not unresolved,
        "none found" if not unresolved else f"offending matches: {quoted(unresolved)}",
    )

    forbidden_found = []
    for forbidden in FORBIDDEN_STRINGS:
        matches = list(re.finditer(re.escape(forbidden), html, flags=re.IGNORECASE))
        if matches:
            forbidden_found.append(
                f"{forbidden!r} found {len(matches)} time(s), first match {matches[0].group(0)!r}"
            )
    report(
        2,
        "forbidden strings absent case-insensitively",
        not forbidden_found,
        "none found" if not forbidden_found else "; ".join(forbidden_found),
    )

    companies = content.get("companies", [])
    expected_urls = [company.get("url", "") for company in companies]
    expected_url_set = set(expected_urls)
    company_hrefs = [value for _, value in parser.hrefs if value in expected_url_set]
    missing_urls = [url for url in expected_urls if url not in company_hrefs]
    companies_pass = len(company_hrefs) == len(companies) and not missing_urls
    company_evidence = f"rows got {len(company_hrefs)}, expected {len(companies)}"
    if missing_urls:
        company_evidence += f"; missing URL hrefs: {quoted(missing_urls)}"
    elif companies_pass:
        company_evidence += "; every expected URL appears as an href"
    report(3, "company row count and URLs", companies_pass, company_evidence)

    invalid_hrefs = [
        f"<{tag}> href={value!r}"
        for tag, value in parser.hrefs
        if not (value.startswith("https://") or value.startswith("#"))
    ]
    report(
        4,
        "every href is https:// or an in-page anchor",
        not invalid_hrefs,
        f"all {len(parser.hrefs)} href values valid"
        if not invalid_hrefs
        else f"offending hrefs: {quoted(invalid_hrefs)}",
    )

    missing_structure = []
    if "viewport" not in parser.meta_names:
        missing_structure.append('meta name="viewport"')
    if parser.h1_count != 1:
        missing_structure.append(f"h1 count got {parser.h1_count}, expected 1")
    if parser.html_lang != "en":
        missing_structure.append(f"html lang got {parser.html_lang!r}, expected 'en'")
    for meta_name in REQUIRED_META:
        if meta_name not in parser.meta_names and meta_name not in parser.meta_properties:
            missing_structure.append(meta_name)
    report(
        5,
        "required structure and meta tags",
        not missing_structure,
        "viewport, one h1, lang='en', and all required social meta tags present"
        if not missing_structure
        else f"missing or incorrect: {quoted(missing_structure)}",
    )

    local_references = [
        f"<{tag}> {attribute}={value!r}"
        for tag, attribute, value in parser.references
        if is_local_reference(value)
    ]
    size_pass = len(html_bytes) <= MAX_BYTES
    references_pass = not local_references
    size_evidence = f"size {len(html_bytes)} bytes, limit {MAX_BYTES} bytes"
    if local_references:
        size_evidence += f"; local references: {quoted(local_references)}"
    else:
        size_evidence += "; no local src/href references"
    report(6, "file size and local references", size_pass and references_pass, size_evidence)

    external_anchors = sum(
        1 for tag, value in parser.hrefs if tag == "a" and value.startswith("https://")
    )
    print(f"ANCHORS {external_anchors}")
    print(f"RESULT: {'PASS' if all(results) else 'FAIL'}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
