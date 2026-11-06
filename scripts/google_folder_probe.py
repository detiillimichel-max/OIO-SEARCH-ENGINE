#!/usr/bin/env python3
"""Single-query diagnostic for Google results containing public Drive folder URLs."""
from __future__ import annotations

import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests

QUERY = "site:drive.google.com/drive/folders filmes"
SEARCH_URL = "https://www.google.com/search?q=" + quote_plus(QUERY) + "&num=20&hl=pt-BR"
OUTPUT = Path("data/discovered-folders/teste-google.json")
REPORT = Path("probe-report.json")
DEBUG = Path("google-response-debug.txt")
TIMEOUT = 25
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
FOLDER_RE = re.compile(r"https?://(?:www\.)?drive\.google\.com/drive/folders/([A-Za-z0-9_-]+)", re.IGNORECASE)


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def unwrap_google_redirect(href: str, base_url: str) -> str:
    value = html.unescape(unquote(href.strip()))
    absolute = urljoin(base_url, value)
    parsed = urlparse(absolute)
    if parsed.hostname and parsed.hostname.endswith("google.com") and parsed.path in {"/url", "/imgres"}:
        params = parse_qs(parsed.query)
        return html.unescape(unquote(params.get("q", params.get("url", params.get("imgurl", [absolute])))[0]))
    return absolute


def normalize_folder_url(value: str) -> str | None:
    value = html.unescape(unquote(value.strip().rstrip(").,;\\"'")))
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"drive.google.com", "www.drive.google.com"}:
        return None
    match = re.fullmatch(r"/drive/folders/([A-Za-z0-9_-]+)/?", parsed.path)
    return f"https://drive.google.com/drive/folders/{match.group(1)}" if match else None


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "query": QUERY, "http_status": None, "final_url": None, "content_type": None,
        "response_bytes": 0, "anchor_count": 0, "drive_folder_mentions": 0,
        "result_count": 0, "page_signals": [], "status": "not_started", "error": None,
    }
    try:
        response = requests.get(
            SEARCH_URL, timeout=TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        report["http_status"] = response.status_code
        report["final_url"] = response.url
        report["content_type"] = response.headers.get("Content-Type", "")
        response.raise_for_status()

        source = response.text
        decoded = html.unescape(source)
        lower = decoded.lower()
        signals = {
            "google_consent": "consent.google.com" in lower or "before you continue to google" in lower,
            "unusual_traffic": "unusual traffic" in lower or "nossos sistemas detectaram tráfego" in lower,
            "captcha": "recaptcha" in lower or "captcha" in lower,
            "google_results_container": "result-stats" in lower or "mnr-c" in lower,
            "drive_folder_text_present": "drive.google.com/drive/folders/" in lower,
        }
        report["page_signals"] = [key for key, value in signals.items() if value]
        report["response_bytes"] = len(response.content)

        parser = AnchorParser()
        parser.feed(source)
        report["anchor_count"] = len(parser.hrefs)

        candidates: list[str] = []
        for href in parser.hrefs:
            candidate = normalize_folder_url(unwrap_google_redirect(href, response.url))
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        report["drive_folder_mentions"] = len(FOLDER_RE.findall(decoded))
        for match in FOLDER_RE.finditer(decoded):
            candidate = normalize_folder_url(match.group(0))
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        OUTPUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["result_count"] = len(candidates)
        report["status"] = "success" if candidates else "no_folder_urls_extracted"

        debug_lines = [
            f"HTTP: {response.status_code}", f"Final URL: {response.url}",
            f"Content-Type: {report['content_type']}", f"Bytes: {report['response_bytes']}",
            f"Anchors: {report['anchor_count']}", f"Drive folder mentions: {report['drive_folder_mentions']}",
            f"Signals: {', '.join(report['page_signals']) or 'none'}",
            f"Extracted folder URLs: {len(candidates)}",
        ]
        snippets = [decoded[max(0, m.start()-180):min(len(decoded), m.end()+180)] for m in list(FOLDER_RE.finditer(decoded))[:10]]
        if snippets:
            debug_lines.append("\n--- Contextos próximos a URLs Drive ---")
            debug_lines.extend(snippets)
        DEBUG.write_text("\n".join(debug_lines) + "\n", encoding="utf-8")

        print(f"Consulta: {QUERY}")
        print(f"HTTP: {response.status_code}")
        print(f"Âncoras HTML: {report['anchor_count']}")
        print(f"Menções a pastas Drive no HTML: {report['drive_folder_mentions']}")
        print(f"URLs de pastas extraídas: {len(candidates)}")
        for url in candidates:
            print(url)
        if not candidates:
            print("Diagnóstico salvo em google-response-debug.txt")
            return 2
        return 0
    except Exception as exc:
        report["status"] = "error"
        report["error"] = str(exc)[:500]
        DEBUG.write_text(f"Falha: {report['error']}\n", encoding="utf-8")
        print(f"FALHA NO TESTE: {report['error']}", file=sys.stderr)
        return 1
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
