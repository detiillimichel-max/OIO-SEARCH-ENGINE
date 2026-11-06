#!/usr/bin/env python3
"""Browser-based single-query probe for Google Drive folder result URLs."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

QUERY = "site:drive.google.com/drive/folders filmes"
SEARCH_URL = "https://www.google.com/search?q=" + quote_plus(QUERY) + "&num=20&hl=pt-BR"
OUTPUT = Path("data/discovered-folders/teste-google.json")
REPORT = Path("probe-report.json")
DEBUG = Path("google-response-debug.txt")
FOLDER_RE = re.compile(r"^/drive/folders/([A-Za-z0-9_-]+)/?$")


def normalize_folder_url(href: str) -> str | None:
    if not href:
        return None
    parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname not in {"drive.google.com", "www.drive.google.com"}:
        return None
    match = FOLDER_RE.fullmatch(parsed.path)
    if not match:
        return None
    return f"https://drive.google.com/drive/folders/{match.group(1)}"


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "query": QUERY,
        "search_url": SEARCH_URL,
        "page_title": "",
        "final_url": "",
        "http_status": None,
        "anchor_count": 0,
        "visible_anchor_count": 0,
        "drive_folder_links": 0,
        "result_count": 0,
        "page_signals": [],
        "status": "not_started",
        "error": None,
    }
    debug: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                locale="pt-BR",
                viewport={"width": 1365, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            response = page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=45000)
            report["http_status"] = response.status if response else None
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except PlaywrightTimeoutError:
                debug.append("Aviso: a página não ficou ociosa em 12 segundos; leitura do DOM continuou.")
            page.wait_for_timeout(2500)

            report["page_title"] = page.title()
            report["final_url"] = page.url
            anchors = page.locator("a").evaluate_all(
                """els => els.map(a => ({
                    href: a.href || a.getAttribute('href') || '',
                    text: (a.innerText || a.getAttribute('aria-label') || '').trim(),
                    visible: !!(a.offsetWidth || a.offsetHeight || a.getClientRects().length)
                }))"""
            )
            report["anchor_count"] = len(anchors)
            report["visible_anchor_count"] = sum(1 for item in anchors if item["visible"])

            candidates: list[str] = []
            relevant_links: list[str] = []
            for item in anchors:
                href = item["href"]
                normalized = normalize_folder_url(href)
                if normalized and normalized not in candidates:
                    candidates.append(normalized)
                if "drive.google.com" in href or "consent.google.com" in href:
                    relevant_links.append(f'{item["text"][:100]} | {href[:300]}')

            body_text = page.locator("body").inner_text(timeout=10000)
            lower = (body_text + " " + report["page_title"]).lower()
            signals = {
                "consent_page": "consent.google.com" in page.url or "before you continue" in lower,
                "captcha_or_robot_check": any(term in lower for term in ("unusual traffic", "not a robot", "captcha", "tráfego incomum")),
                "javascript_interstitial": "enablejs" in page.url.lower() or "javascript" in lower and "google search" in lower,
                "search_results_visible": bool(page.locator("#search").count()) or bool(page.locator("#rso").count()),
                "drive_folder_text_visible": "drive.google.com/drive/folders/" in body_text,
            }
            report["page_signals"] = [key for key, value in signals.items() if value]
            report["drive_folder_links"] = len(candidates)
            report["result_count"] = len(candidates)
            report["status"] = "success" if candidates else "no_folder_urls_extracted"

            OUTPUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            debug.extend([
                f"Consulta: {QUERY}",
                f"HTTP: {report['http_status']}",
                f"URL final: {report['final_url']}",
                f"Título: {report['page_title']}",
                f"Links DOM: {report['anchor_count']}",
                f"Links visíveis: {report['visible_anchor_count']}",
                f"Links de pastas Drive: {report['drive_folder_links']}",
                f"Sinais: {', '.join(report['page_signals']) or 'nenhum identificado'}",
                "",
                "--- Links Drive/consentimento vistos no navegador ---",
                *(relevant_links[:30] or ["(nenhum)"]),
                "",
                "--- Texto visível da página (primeiros 5000 caracteres) ---",
                body_text[:5000],
            ])
            browser.close()

        print(f"Consulta: {QUERY}")
        print(f"Título da página: {report['page_title']}")
        print(f"HTTP: {report['http_status']}")
        print(f"Links no DOM: {report['anchor_count']}")
        print(f"URLs de pastas extraídas: {report['result_count']}")
        for url in candidates:
            print(url)
        if not candidates:
            print("Nenhuma URL encontrada. Diagnóstico salvo em google-response-debug.txt")
            return 2
        return 0
    except Exception as exc:
        report["status"] = "error"
        report["error"] = str(exc)[:500]
        debug.append(f"Erro: {report['error']}")
        print(f"FALHA NO TESTE: {report['error']}", file=sys.stderr)
        return 1
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        DEBUG.write_text("\n".join(debug) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
