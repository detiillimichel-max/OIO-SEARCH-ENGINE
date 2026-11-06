#!/usr/bin/env python3
"""Discover and test public SearXNG instances listed by searx.space.

Only sends a harmless, fixed test query. Results are diagnostic metadata;
this script does not scrape result content or bypass access controls.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

SOURCE_URL = "https://searx.space/data/instances.json"
OUTPUT = Path("data/searxng-instances.json")
MAX_INSTANCES = int(os.getenv("MAX_INSTANCES", "30"))
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))
WORKERS = int(os.getenv("WORKERS", "4"))
TEST_QUERY = "SearXNG"
USER_AGENT = "OIO-SEARCH-ENGINE-instance-checker/1.0 (public instance availability test)"


def clean_base_url(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    return value.rstrip("/")


def load_instances() -> list[str]:
    response = requests.get(
        SOURCE_URL,
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    raw = payload.get("instances", {})
    if not isinstance(raw, dict):
        raise ValueError("Formato inesperado em searx.space: 'instances' não é um objeto.")

    urls: list[str] = []
    for key, metadata in raw.items():
        if not isinstance(metadata, dict):
            continue
        # searx.space normally uses the instance URL as the object key.
        base = clean_base_url(key)
        if not base:
            continue
        urls.append(base)

    return sorted(set(urls))[:MAX_INSTANCES]


def check_instance(base_url: str) -> dict:
    started = time.monotonic()
    checked_at = datetime.now(timezone.utc).isoformat()
    record = {
        "url": base_url,
        "checked_at": checked_at,
        "http_status": None,
        "response_ms": None,
        "json_search": False,
        "results_count": 0,
        "status": "unavailable",
        "error": None,
    }
    try:
        response = requests.get(
            f"{base_url}/search",
            params={"q": TEST_QUERY, "format": "json"},
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        record["http_status"] = response.status_code
        record["response_ms"] = round((time.monotonic() - started) * 1000)

        if response.status_code != 200:
            record["status"] = "http_error"
            record["error"] = f"HTTP {response.status_code}"
            return record

        content_type = response.headers.get("Content-Type", "").lower()
        if "json" not in content_type:
            record["status"] = "json_disabled_or_blocked"
            return record

        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list):
            record["status"] = "unexpected_json"
            return record

        record["json_search"] = True
        record["results_count"] = len(results)
        record["status"] = "online_json"
        return record
    except requests.Timeout:
        record["status"] = "timeout"
        record["error"] = f"Timeout após {TIMEOUT}s"
    except requests.RequestException as exc:
        record["status"] = "connection_error"
        record["error"] = str(exc)[:240]
    except (ValueError, json.JSONDecodeError) as exc:
        record["status"] = "invalid_json"
        record["error"] = str(exc)[:240]
    return record


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    urls = load_instances()
    print(f"Instâncias HTTPS encontradas: {len(urls)}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        records = list(pool.map(check_instance, urls))

    records.sort(key=lambda item: (item["status"] != "online_json", item["response_ms"] or 999999))
    online = sum(item["status"] == "online_json" for item in records)
    report = {
        "project": "OIO-SEARCH-ENGINE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_URL,
        "tested": len(records),
        "online_json": online,
        "instances": records,
        "notes": [
            "A disponibilidade é apenas um retrato do momento do teste.",
            "Instâncias públicas podem limitar, bloquear ou desativar JSON.",
            "Resultados não são armazenados; somente metadados de diagnóstico.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Teste concluído: {online}/{len(records)} instâncias responderam com JSON.")
    print(f"Relatório salvo em {OUTPUT}")


if __name__ == "__main__":
    main()
