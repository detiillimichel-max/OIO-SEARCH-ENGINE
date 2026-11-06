#!/usr/bin/env python3
"""One-query Google Drive folder discovery probe.

Fetches one ordinary Google results page. It does not open Drive folders,
download files, inspect media, bypass CAPTCHAs, or rotate identities.
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

QUERY = "site:drive.google.com/drive/folders filmes"
SEARCH_URL = "https://www.google.com/search?q=" + quote_plus(QUERY) + "&num=20&hl=pt-BR"
OUTPUT = Path("data/discovered-folders/teste-google.json")
REPORT = Path("probe-report.json")
TIMEOUT = 25
USER_AGENT = "Mozilla/5.0 (compatible; OIO-SEARCH-ENGINE/1.0; +https://github.com/detiillimichel-max/OIO-SEARCH-ENGINE)"


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def unwrap_google_redirect(href: str) -> str:
    value = unquote(href)
    parsed = urlparse(value)
    if parsed.path == "/url":
        params = parse_qs(parsed.query)
        value = params.get("q", params.get("url", [value]))[0]
    return unquote(value)


def is_drive_folder_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"drive.google.com", "www.drive.google.com"}
        and re.fullmatch(r"/drive/folders/[A-Za-z0-9_-]+/?", parsed.path) is not None
    )


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "query": QUERY,
        "search_url": SEARCH_URL,
        "http_status": None,
        "result_count": 0,
        "status": "not_started",
        "error": None,
    }
    try:
        response = requests.get(
            SEARCH_URL,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
        )
        report["http_status"] = response.status_code
        response.raise_for_status()

        html = response.text
        lowered = html.lower()
        if any(marker in lowered for marker in ("unusual traffic", " nossos sistemas detectaram tráfego", "/sorry/")):
            raise RuntimeError("Google apresentou uma página de bloqueio/validação; nenhuma tentativa de contornar foi feita.")

        parser = AnchorParser()
        parser.feed(html)
        found: list[str] = []
        for href in parser.hrefs:
            candidate = unwrap_google_redirect(href)
            if is_drive_folder_url(candidate):
                normalized = candidate.rstrip("/")
                if normalized not in found:
                    found.append(normalized)

        OUTPUT.write_text(json.dumps(found, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["result_count"] = len(found)
        report["status"] = "success" if found else "no_folder_urls_in_google_response"
        report["output"] = str(OUTPUT)
        print(f"Consulta: {QUERY}")
        print(f"HTTP: {response.status_code}")
        print(f"URLs de pastas encontradas: {len(found)}")
        for url in found:
            print(url)
        if not found:
            print("Google respondeu, mas não foram extraídas URLs de pastas nesta resposta.")
            return 2
        return 0
    except Exception as exc:
        report["status"] = "error"
        report["error"] = str(exc)[:500]
        print(f"FALHA NO TESTE: {report['error']}", file=sys.stderr)
        return 1
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
