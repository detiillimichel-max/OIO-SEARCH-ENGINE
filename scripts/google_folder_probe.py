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
        self.title_parts: list[str] = []
        self.in_title = False
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        if tag.lower() == "a" and attrs_dict.get("href"):
            self.hrefs.append(attrs_dict["href"])
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.text_parts.append(cleaned)
            if self.in_title:
                self.title_parts.append(cleaned)


def unwrap_google_redirect(href: str, base_url: str) -> str:
    absolute = urljoin(base_url, html.unescape(unquote(href.strip())))
    parsed = urlparse(absolute)
    if parsed.hostname and parsed.hostname.endswith("google.com") and parsed.path in {"/url", "/imgres"}:
        params = parse_qs(parsed.query)
        target = params.get("q", params.get("url", params.get("imgurl", [absolute])))[0]
        return html.unescape(unquote(target))
    return absolute


def normalize_folder_url(value: str) -> str | None:
    value = html.unescape(unquote(value.strip())).rstrip(").,;")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname not in {"drive.google.com", "www.drive.google.com"}:
        return None
    match = re.fullmatch(r"/drive/folders/([A-Za-z0-9_-]+)/?", parsed.path)
    if not match:
        return None
    return f"https://drive.google.com/drive/folders/{match.group(1)}"


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "query": QUERY, "http_status": None, "final_url": None, "content_type": None,
        "response_bytes": 0, "anchor_count": 0, "drive_folder_mentions": 0,
        "result_count": 0, "page_signals": [], "page_title": "", "status": "not_started", "error": None,
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
            "google_search_app": "google search" in lower or "www.google.com/search" in lower,
        }
        report["page_signals"] = [key for key, value in signals.items() if value]
        report["response_bytes"] = len(response.content)

        parser = AnchorParser()
        parser.feed(source)
        report["anchor_count"] = len(parser.hrefs)
        report["page_title"] = " ".join(parser.title_parts)[:200]

        candidates: list[str] = []
        anchor_debug: list[str] = []
        for href in parser.hrefs:
            resolved = unwrap_google_redirect(href, response.url)
            parsed_resolved = urlparse(resolved)
            anchor_debug.append(f"{parsed_resolved.netloc}{parsed_resolved.path}"[:240])
            candidate = normalize_folder_url(resolved)
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

        text_samples = [item for item in parser.text_parts if any(term in item.lower() for term in ("filme", "drive", "google", "resultado", "result"))]
        debug_lines = [
            f"HTTP: {response.status_code}", f"Final URL: {response.url}",
            f"Content-Type: {report['content_type']}", f"Bytes: {report['response_bytes']}",
            f"Page title: {report['page_title'] or '(sem title)'}",
            f"Anchors: {report['anchor_count']}", f"Drive folder mentions: {report['drive_folder_mentions']}",
            f"Signals: {', '.join(report['page_signals']) or 'none'}",
            f"Extracted folder URLs: {len(candidates)}",
            "", "--- Destinos dos links encontrados (sem parâmetros) ---",
            *(anchor_debug[:20] or ["(nenhum)"]),
            "", "--- Trechos de texto relevantes ---",
            *(text_samples[:30] or ["(nenhum)"]),
        ]
        DEBUG.write_text("\n".join(debug_lines) + "\n", encoding="utf-8")

        print(f"Consulta: {QUERY}")
        print(f"HTTP: {response.status_code}")
        print(f"Âncoras HTML: {report['anchor_count']}")
        print(f"Menções a pastas Drive no HTML: {report['drive_folder_mentions']}")
        print(f"URLs de pastas extraídas: {len(candidates)}")
        for url in candidates:
            print(url)
        if not candidates:
            print("Diagnóstico ampliado salvo em google-response-debug.txt")
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
