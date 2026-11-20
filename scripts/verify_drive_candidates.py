#!/usr/bin/env python3
"""Verify Google Drive candidate pages without downloading media.

A reachable HTML page is not proof of anonymous access. The verifier only
inspects a small HTML response and never follows redirects outside Google.
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INPUT = DATA / "discovery-candidates.json"
OUTPUT = DATA / "drive-verification-report.json"
TIMEOUT = int(os.getenv("VERIFY_TIMEOUT_SECONDS", "15"))
MAX_ITEMS = int(os.getenv("MAX_VERIFY_ITEMS", "250"))
WORKERS = max(1, min(int(os.getenv("VERIFY_WORKERS", "4")), 6))
DELAY = float(os.getenv("VERIFY_DELAY_SECONDS", "0.4"))
MAX_HTML_BYTES = 64 * 1024
MAX_REDIRECTS = 5
ALLOWED_HOSTS = {
    "drive.google.com",
    "www.drive.google.com",
    "accounts.google.com",
    "docs.google.com",
}
USER_AGENT = "OIO-SEARCH-ENGINE/1.0 (+https://github.com/detiillimichel-max/OIO-SEARCH-ENGINE)"
LOGIN_MARKERS = (
    "accounts.google.com",
    "sign in - google accounts",
    "sign in to continue to google drive",
    "you need to sign in",
)
RESTRICTED_MARKERS = (
    "you need access",
    "request access",
    "you don't have access",
    "you do not have access",
    "access denied",
)
NOT_FOUND_MARKERS = (
    "file you have requested does not exist",
    "sorry, the file you have requested does not exist",
    "404. that’s an error",
    "404 not found",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def safe_google_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS
    except (TypeError, ValueError):
        return False


def inspect_candidate(item: dict) -> dict:
    url = item.get("url", "")
    result = {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "url": url,
        "checked_at": utc_now(),
        "verification_status": "unknown",
        "http_status": None,
        "final_url": None,
        "content_type": None,
        "evidence": "Sem evidência suficiente.",
        "anonymous_access_confirmed": False,
        "media_downloaded": False,
    }
    if not safe_google_url(url):
        result.update(
            verification_status="invalid_url",
            evidence="URL fora da lista permitida de domínios Google Drive.",
        )
        return result

    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if not safe_google_url(current):
                result.update(
                    verification_status="redirect_outside_google",
                    final_url=current,
                    evidence="Redirecionamento para domínio fora da lista permitida; não seguido.",
                )
                return result

            with requests.get(
                current,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Range": f"bytes=0-{MAX_HTML_BYTES - 1}",
                },
                timeout=TIMEOUT,
                allow_redirects=False,
                stream=True,
            ) as response:
                result["http_status"] = response.status_code
                result["content_type"] = response.headers.get("Content-Type", "")[:160]

                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        result.update(
                            verification_status="unknown",
                            evidence="Resposta de redirecionamento sem destino.",
                        )
                        return result
                    current = urljoin(current, location)
                    continue

                result["final_url"] = current
                status = response.status_code

                if status in (401, 403):
                    result.update(
                        verification_status="restricted",
                        evidence=f"Servidor respondeu HTTP {status}.",
                    )
                    return result
                if status == 404 or status == 410:
                    result.update(
                        verification_status="unavailable",
                        evidence=f"Servidor respondeu HTTP {status}.",
                    )
                    return result
                if status == 429:
                    result.update(
                        verification_status="rate_limited",
                        evidence="Limite temporário de requisições; verificar novamente depois.",
                    )
                    return result
                if status >= 500:
                    result.update(
                        verification_status="temporary_error",
                        evidence=f"Erro temporário do servidor: HTTP {status}.",
                    )
                    return result
                if status not in (200, 206):
                    result.update(
                        verification_status="unknown",
                        evidence=f"Resposta HTTP {status}; não foi possível classificar.",
                    )
                    return result

                content_type = (response.headers.get("Content-Type") or "").lower()
                if "text/html" not in content_type and "application/xhtml" not in content_type:
                    result.update(
                        verification_status="unknown",
                        evidence="Resposta não identificada como página HTML; conteúdo não foi baixado.",
                    )
                    return result

                body = bytearray()
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        break
                    remaining = MAX_HTML_BYTES - len(body)
                    body.extend(chunk[:remaining])
                    if len(body) >= MAX_HTML_BYTES:
                        break
                html = body.decode("utf-8", errors="ignore").lower()

                if any(marker in html for marker in LOGIN_MARKERS) or "accounts.google.com" in current:
                    result.update(
                        verification_status="login_required",
                        evidence="A página indica necessidade de login.",
                    )
                    return result
                if any(marker in html for marker in RESTRICTED_MARKERS):
                    result.update(
                        verification_status="restricted",
                        evidence="A página contém indicação de solicitação ou falta de permissão.",
                    )
                    return result
                if any(marker in html for marker in NOT_FOUND_MARKERS):
                    result.update(
                        verification_status="unavailable",
                        evidence="A página indica que o item não existe ou não está disponível.",
                    )
                    return result

                result.update(
                    verification_status="page_reachable_unverified",
                    evidence="Página HTML respondeu, mas não foi possível confirmar visualização anônima.",
                )
                return result

        result.update(
            verification_status="redirect_limit",
            evidence=f"Mais de {MAX_REDIRECTS} redirecionamentos.",
        )
        return result

    except requests.Timeout:
        result.update(verification_status="timeout", evidence="Tempo limite da requisição excedido.")
    except requests.RequestException as exc:
        result.update(verification_status="network_error", evidence=str(exc)[:240])
    except Exception as exc:
        result.update(verification_status="verification_error", evidence=str(exc)[:240])
    return result


def main() -> int:
    payload = load_json(INPUT)
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("O catálogo não contém uma lista 'items' válida.")

    selected = items[:MAX_ITEMS]
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(inspect_candidate, item) for item in selected]
        for future in as_completed(futures):
            results.append(future.result())
            if DELAY > 0:
                time.sleep(DELAY / WORKERS)

    results.sort(key=lambda row: row.get("url", ""))
    counts = {}
    for row in results:
        status = row["verification_status"]
        counts[status] = counts.get(status, 0) + 1

    report = {
        "schema_version": 1,
        "project": "OIO-SEARCH-ENGINE",
        "checked_at": utc_now(),
        "catalog_total": len(items),
        "checked_total": len(results),
        "not_checked_total": max(0, len(items) - len(results)),
        "status_counts": counts,
        "items": results,
        "important": (
            "page_reachable_unverified NÃO significa acesso público confirmado. "
            "HTTP 200 não prova permissão anônima. Nenhum vídeo foi baixado. "
            "authorized e playback_ready permanecem false."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Candidatos no catálogo: {len(items)}")
    print(f"Candidatos verificados: {len(results)}")
    print("Resumo por status:")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    print("Nenhum vídeo foi baixado; acesso anônimo não é presumido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
