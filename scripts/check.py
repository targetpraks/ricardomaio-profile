#!/usr/bin/env python3
"""Independently check the rendered landing page and AI layer against CONTRACT-V2.md."""

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
        self.meta_robots = []
        self.json_ld_blocks = []
        self.company_names = []
        self._json_ld_parts = None
        self._co_name_parts = None

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
                if name.lower() == "robots":
                    self.meta_robots.append(attributes.get("content") or "")
            if property_name is not None:
                self.meta_properties.add(property_name)
        elif tag == "script":
            script_type = (attributes.get("type") or "").strip().lower()
            if script_type == "application/ld+json":
                self._json_ld_parts = []
                self.json_ld_blocks.append(self._json_ld_parts)

        if tag == "span" and "co-name" in (attributes.get("class") or "").split():
            self._co_name_parts = []

        for attribute in ("href", "src"):
            if attribute not in attributes:
                continue
            value = attributes[attribute]
            value = "" if value is None else value
            self.references.append((tag, attribute, value))
            if attribute == "href":
                self.hrefs.append((tag, value))

    def handle_data(self, data):
        if self._json_ld_parts is not None:
            self._json_ld_parts.append(data)
        if self._co_name_parts is not None:
            self._co_name_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self._json_ld_parts = None
        elif tag == "span" and self._co_name_parts is not None:
            self.company_names.append("".join(self._co_name_parts).strip())
            self._co_name_parts = None


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


def robot_directives(text):
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        field, separator, value = line.partition(":")
        if separator:
            yield field.strip().lower(), value.strip()


def crawler_explicitly_allowed(text, agent):
    groups = []
    agents = []
    rules = []
    in_rules = False

    for field, value in robot_directives(text):
        if field == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents = []
                rules = []
                in_rules = False
            agents.append(value.lower())
        elif field in ("allow", "disallow") and agents:
            rules.append((field, value))
            in_rules = True

    if agents:
        groups.append((agents, rules))

    expected_agent = agent.lower()
    return any(
        expected_agent in group_agents
        and any(field == "allow" and value == "/" for field, value in group_rules)
        for group_agents, group_rules in groups
    )


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

    person = content.get("person", {})
    meta = content.get("meta", {})
    site_url = str(meta.get("site_url", "")).rstrip("/")
    canonical_url = f"{site_url}/" if site_url else ""

    json_ld_texts = ["".join(parts) for parts in parser.json_ld_blocks]
    json_ld_data = None
    json_ld_error = None
    if len(json_ld_texts) == 1:
        try:
            json_ld_data = json.loads(json_ld_texts[0])
        except json.JSONDecodeError as error:
            json_ld_error = str(error)

    json_ld_syntax_pass = len(json_ld_texts) == 1 and json_ld_error is None
    if len(json_ld_texts) != 1:
        json_ld_syntax_evidence = (
            f"script count got {len(json_ld_texts)}, expected exactly 1 "
            'script type="application/ld+json"'
        )
    elif json_ld_error is not None:
        json_ld_syntax_evidence = f"script count 1; JSON error: {json_ld_error}"
    else:
        json_ld_syntax_evidence = (
            f"script count 1; JSON parsed successfully as {type(json_ld_data).__name__}"
        )
    report(
        7,
        "exactly one JSON-LD script with valid JSON",
        json_ld_syntax_pass,
        json_ld_syntax_evidence,
    )

    if not isinstance(json_ld_data, dict):
        identity_evidence = (
            "no parsed JSON-LD object; @type, name and address.addressLocality cannot match"
        )
        identity_pass = False
    else:
        address = json_ld_data.get("address")
        if not isinstance(address, dict):
            address = {}
        identity_mismatches = []
        for label, actual, expected in (
            ("@type", json_ld_data.get("@type"), "Person"),
            ("name", json_ld_data.get("name"), person.get("name")),
            ("address.addressLocality", address.get("addressLocality"), person.get("city")),
        ):
            if actual != expected:
                identity_mismatches.append(f"{label} got {actual!r}, expected {expected!r}")
        identity_pass = not identity_mismatches
        identity_evidence = (
            f"@type='Person'; name={person.get('name')!r}; "
            f"addressLocality={person.get('city')!r}"
            if identity_pass
            else "; ".join(identity_mismatches)
        )
    report(8, "JSON-LD Person identity and locality", identity_pass, identity_evidence)

    if not isinstance(json_ld_data, dict) or not isinstance(json_ld_data.get("owns"), list):
        owns_pass = False
        owns_evidence = "JSON-LD owns is unavailable or is not an array"
    else:
        owns = json_ld_data["owns"]
        organization_count = sum(
            1
            for organization in owns
            if isinstance(organization, dict) and organization.get("@type") == "Organization"
        )
        owns_urls = [
            organization.get("url") for organization in owns if isinstance(organization, dict)
        ]
        missing_owns_urls = [url for url in expected_urls if url not in owns_urls]
        owns_pass = (
            len(owns) == len(companies)
            and organization_count == len(companies)
            and not missing_owns_urls
        )
        owns_evidence = (
            f"owns entries got {len(owns)}, Organization objects got {organization_count}, "
            f"expected {len(companies)}"
        )
        if missing_owns_urls:
            owns_evidence += f"; missing company URLs: {quoted(missing_owns_urls)}"
        elif owns_pass:
            owns_evidence += "; every company URL appears in owns"
    report(9, "JSON-LD owns one Organization per company", owns_pass, owns_evidence)

    draft = bool(meta.get("draft", False))
    noindex_present = any(
        re.search(r"\bnoindex\b", robots_content, flags=re.IGNORECASE)
        for robots_content in parser.meta_robots
    )
    noindex_pass = noindex_present == draft
    noindex_evidence = f"meta.draft={draft}; noindex {'present' if noindex_present else 'absent'}"
    noindex_evidence += "; matches draft flag" if noindex_pass else "; does not match draft flag"
    report(10, "noindex follows content meta.draft", noindex_pass, noindex_evidence)

    ai_file_names = ("llms.txt", "robots.txt", "sitemap.xml", "profile.json")
    ai_texts = {}
    ai_errors = {}
    for file_name in ai_file_names:
        ai_path = html_path.parent / file_name
        try:
            ai_texts[file_name] = ai_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            ai_errors[file_name] = f"missing at {ai_path}"
        except (OSError, UnicodeError) as error:
            ai_errors[file_name] = f"unreadable at {ai_path}: {error}"

    ai_files_pass = not ai_errors
    ai_files_evidence = (
        f"all four AI files found beside {html_path}"
        if ai_files_pass
        else "; ".join(f"{name} {ai_errors[name]}" for name in ai_file_names if name in ai_errors)
    )
    report(11, "AI layer files exist beside the HTML", ai_files_pass, ai_files_evidence)

    llms_text = ai_texts.get("llms.txt")
    if llms_text is None:
        llms_pass = False
        llms_evidence = f"llms.txt {ai_errors.get('llms.txt', 'was not read')}"
    else:
        missing_llms = []
        for company in companies:
            for key in ("name", "url"):
                value = company.get(key, "")
                if not value or value not in llms_text:
                    missing_llms.append(f"company {key} {value!r}")
        if not canonical_url or canonical_url not in llms_text:
            missing_llms.append(f"canonical URL {canonical_url!r}")
        llms_pass = not missing_llms
        llms_evidence = (
            f"all {len(companies)} company names and URLs plus canonical {canonical_url!r} present"
            if llms_pass
            else f"missing from llms.txt: {quoted(missing_llms)}"
        )
    report(12, "llms.txt company and canonical coverage", llms_pass, llms_evidence)

    robots_text = ai_texts.get("robots.txt")
    if robots_text is None:
        robots_pass = False
        robots_evidence = f"robots.txt {ai_errors.get('robots.txt', 'was not read')}"
    else:
        crawler_status = {
            agent: crawler_explicitly_allowed(robots_text, agent)
            for agent in ("GPTBot", "ClaudeBot")
        }
        expected_sitemap_url = f"{canonical_url}sitemap.xml" if canonical_url else ""
        sitemap_values = [
            value for field, value in robot_directives(robots_text) if field == "sitemap"
        ]
        sitemap_directive_pass = bool(expected_sitemap_url) and expected_sitemap_url in sitemap_values
        robots_pass = all(crawler_status.values()) and sitemap_directive_pass
        robots_evidence = "; ".join(
            f"{agent} explicit Allow: /={allowed}" for agent, allowed in crawler_status.items()
        )
        robots_evidence += (
            f"; Sitemap {expected_sitemap_url!r} "
            f"{'present' if sitemap_directive_pass else 'missing or incorrect'}"
        )
        if sitemap_values and not sitemap_directive_pass:
            robots_evidence += f"; got {quoted(sitemap_values)}"
    report(13, "robots.txt AI crawler access and sitemap", robots_pass, robots_evidence)

    sitemap_text = ai_texts.get("sitemap.xml")
    if sitemap_text is None:
        sitemap_pass = False
        sitemap_evidence = f"sitemap.xml {ai_errors.get('sitemap.xml', 'was not read')}"
    else:
        sitemap_pass = bool(canonical_url) and canonical_url in sitemap_text
        sitemap_evidence = (
            f"canonical URL {canonical_url!r} present"
            if sitemap_pass
            else f"canonical URL {canonical_url!r} not found in {html_path.parent / 'sitemap.xml'}"
        )
    report(14, "sitemap.xml contains the canonical URL", sitemap_pass, sitemap_evidence)

    profile_text = ai_texts.get("profile.json")
    profile_data = None
    profile_error = None
    if profile_text is not None:
        try:
            profile_data = json.loads(profile_text)
        except json.JSONDecodeError as error:
            profile_error = str(error)

    if profile_text is None:
        profile_pass = False
        profile_evidence = f"profile.json {ai_errors.get('profile.json', 'was not read')}"
    elif profile_error is not None:
        profile_pass = False
        profile_evidence = f"profile.json JSON error: {profile_error}"
    elif not isinstance(profile_data, dict) or not isinstance(profile_data.get("companies"), list):
        profile_pass = False
        profile_evidence = "profile.json must be an object with a companies array"
    else:
        profile_companies = profile_data["companies"]
        profile_names = [
            company.get("name") for company in profile_companies if isinstance(company, dict)
        ]
        profile_urls = [
            company.get("url") for company in profile_companies if isinstance(company, dict)
        ]
        missing_profile_names = [
            company.get("name", "")
            for company in companies
            if company.get("name", "") not in profile_names
        ]
        missing_profile_urls = [url for url in expected_urls if url not in profile_urls]
        profile_pass = (
            len(profile_companies) == len(companies)
            and not missing_profile_names
            and not missing_profile_urls
        )
        profile_evidence = (
            f"valid JSON; companies got {len(profile_companies)}, expected {len(companies)}"
        )
        missing_profile_evidence = []
        if missing_profile_names:
            missing_profile_evidence.append(f"names: {quoted(missing_profile_names)}")
        if missing_profile_urls:
            missing_profile_evidence.append(f"URLs: {quoted(missing_profile_urls)}")
        if missing_profile_evidence:
            profile_evidence += "; missing " + "; ".join(missing_profile_evidence)
        elif profile_pass:
            profile_evidence += "; every company name and URL present"
    report(15, "profile.json parses and lists every company", profile_pass, profile_evidence)

    papa_pasta = next(
        (company for company in companies if company.get("name") == "Papa Pasta"), None
    )
    papa_pasta_url = papa_pasta.get("url", "") if papa_pasta else ""
    papa_name_pass = "Papa Pasta" in parser.company_names
    papa_url_pass = bool(papa_pasta_url) and any(
        value == papa_pasta_url for _, value in parser.hrefs
    )
    papa_evidence = (
        f".co-name 'Papa Pasta' {'present' if papa_name_pass else 'missing'}; "
        f"href {papa_pasta_url!r} {'present' if papa_url_pass else 'missing'}"
    )
    report(
        16,
        "Papa Pasta appears as .co-name and URL href",
        papa_name_pass and papa_url_pass,
        papa_evidence,
    )

    external_anchors = sum(
        1 for tag, value in parser.hrefs if tag == "a" and value.startswith("https://")
    )
    print(f"ANCHORS {external_anchors}")
    print(f"RESULT: {'PASS' if all(results) else 'FAIL'}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
