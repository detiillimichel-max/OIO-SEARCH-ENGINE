#!/usr/bin/env python3
"""Continuous, polite discovery of publicly indexed Google Drive URLs.

This collector stores candidates only. A discovered URL is NOT proof of public
permission, copyright clearance, or playback support. It never downloads media.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = DATA / "discovery-candidates.json"
STATE = DATA / "discovery-state.json"
SEARXNG_REPORT = DATA / "searxng-instances.json"
USER_AGENT = "OIO-SEARCH-ENGINE/1.0 (+https://github.com/detiillimichel-max/OIO-SEARCH-ENGINE)"
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
MAX_CRAWLS = int(os.getenv("MAX_COMMONCRAWL_INDEXES", "2"))
MAX_PER_PATTERN = int(os.getenv("MAX_RESULTS_PER_PATTERN", "100"))
MAX_SEARCH_QUERIES = int(os.getenv("MAX_SEARCH_QUERIES", "6"))
DELAY = float(os.getenv("SEARCH_DELAY_SECONDS", "2"))
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

PATTERNS = (
    ("folders", "drive.google.com/drive/folders/*"),
    ("legacy_folders", "drive.google.com/drive/u/*/folders/*"),
    ("files", "drive.google.com/file/d/*"),
    ("open_links", "drive.google.com/open?id=*"),
)
DORKS = (
    'site:drive.google.com/drive/folders "video"',
    'site:drive.google.com/drive/folders "filmes"',
    'site:drive.google.com/drive/folders "desenhos"',
    'site:drive.google.com/drive/folders "documentários"',
    'site:drive.google.com/file/d/ "mp4"',
    'site:drive.google.com/drive/folders "coleção" OR "acervo"',
)
DRIVE_HOSTS = {"drive.google.com", "www.drive.google.com"}
FOLDER_RE = re.compile(r"^/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)$")
FILE_RE = re.compile(r"^/file/d/([A-Za-z0-9_-]+)(?:/.*)?$")
LEGACY_RE = re.compile(r"^/open$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_drive_url(raw: str) -> dict | None:
    try:
        parsed = urlparse(raw.strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in DRIVE_HOSTS:
        return None
    folder = FOLDER_RE.fullmatch(parsed.path.rstrip("/"))
    file_match = FILE_RE.fullmatch(parsed.path)
    if folder:
        kind, item_id = "folder", folder.group(1)
        canonical = f"https://drive.google.com/drive/folders/{item_id}"
    elif file_match:
        kind, item_id = "file", file_match.group(1)
        canonical = f"https://drive.google.com/file/d/{item_id}/view"
    elif LEGACY_RE.fullmatch(parsed.path) and parsed.query:
        from urllib.parse import parse_qs
        item_id = parse_qs(parsed.query).get("id", [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", item_id):
            return None
        kind, canonical = "file", f"https://drive.google.com/open?id={item_id}"
    else:
        return None
    return {
        "id": item_id,
        "kind": kind,
        "url": canonical,
        "source": "public_index",
        "access_status": "unverified",
        "publication_status": "candidate_only",
        "discovered_at": now(),
        "authorized": False,
        "playback_ready": False,
    }


def commoncrawl_indexes() -> list[dict]:
    response = SESSION.get("https://index.commoncrawl.org/collinfo.json", timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data[:MAX_CRAWLS] if isinstance(data, list) else []


def search_commoncrawl() -> tuple[list[dict], list[dict]]:
    found, diagnostics = [], []
    try:
        indexes = commoncrawl_indexes()
    except requests.RequestException as exc:
        return found, [{"provider": "commoncrawl", "status": "unavailable", "error": str(exc)[:240]}]
    for index in indexes:
        api = index.get("cdx-api")
        crawl = index.get("id", "unknown")
        if not api:
            continue
        for label, pattern in PATTERNS:
            try:
                response = SESSION.get(
                    api,
                    params={
                        "url": pattern,
                        "output": "json",
                        "filter": "status:200",
                        "fl": "url,timestamp,status,mime",
                        "limit": MAX_PER_PATTERN,
                    },
                    timeout=TIMEOUT,
                )
                if response.status_code == 404:
                    diagnostics.append({"provider": "commoncrawl", "crawl": crawl, "pattern": label, "status": "no_matches"})
                    continue
                response.raise_for_status()
                count = 0
                for line in response.text.splitlines():
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    candidate = normalize_drive_url(record.get("url", ""))
                    if candidate:
                        candidate["index"] = crawl
                        candidate["capture_timestamp"] = record.get("timestamp")
                        candidate["mime"] = record.get("mime")
                        candidate["discovery_method"] = f"commoncrawl:{label}"
                        found.append(candidate)
                        count += 1
                diagnostics.append({"provider": "commoncrawl", "crawl": crawl, "pattern": label, "status": "ok", "candidates": count})
            except requests.RequestException as exc:
                diagnostics.append({"provider": "commoncrawl", "crawl": crawl, "pattern": label, "status": "error", "error": str(exc)[:200]})
            time.sleep(DELAY)
    return found, diagnostics


def active_searxng_instances() -> list[str]:
    report = load_json(SEARXNG_REPORT, {})
    records = report.get("instances", []) if isinstance(report, dict) else []
    urls = []
    for item in records:
        if isinstance(item, dict) and item.get("status") == "online_json" and isinstance(item.get("url"), str):
            base = item["url"].rstrip("/")
            if base.startswith("https://"):
                urls.append(base)
    return list(dict.fromkeys(urls))


def search_searxng() -> tuple[list[dict], list[dict]]:
    found, diagnostics = [], []
    instances = active_searxng_instances()
    if not instances:
        return found, [{"provider": "searxng", "status": "skipped", "reason": "Nenhuma instância HTTPS com JSON validado no relatório atual."}]
    attempts = 0
    for query in DORKS:
        if attempts >= MAX_SEARCH_QUERIES:
            break
        # Rotate instances per query so one failing host does not stop discovery.
        base = instances[attempts % len(instances)]
        attempts += 1
        try:
            response = SESSION.get(
                f"{base}/search",
                params={"q": query, "format": "json", "language": "pt-BR"},
                timeout=TIMEOUT,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results", [])
            count = 0
            for item in results if isinstance(results, list) else []:
                candidate = normalize_drive_url(item.get("url", ""))
                if candidate:
                    candidate["title"] = (item.get("title") or "")[:300]
                    candidate["description"] = (item.get("content") or "")[:700]
                    candidate["discovery_method"] = "searxng:dork"
                    candidate["search_query"] = query
                    found.append(candidate)
                    count += 1
            diagnostics.append({"provider": "searxng", "instance": base, "query": query, "status": "ok", "candidates": count})
        except (requests.RequestException, ValueError) as exc:
            diagnostics.append({"provider": "searxng", "instance": base, "query": query, "status": "error", "error": str(exc)[:200]})
        time.sleep(DELAY)
    return found, diagnostics


def merge_candidates(items: list[dict], previous: list[dict]) -> list[dict]:
    merged = {}
    for item in previous + items:
        key = item.get("url")
        if key:
            if key in merged:
                methods = set(merged[key].get("discovery_methods", []))
                methods.add(item.get("discovery_method", "unknown"))
                merged[key]["discovery_methods"] = sorted(methods)
                for field in ("title", "description", "capture_timestamp", "mime"):
                    if item.get(field) and not merged[key].get(field):
                        merged[key][field] = item[field]
            else:
                item = dict(item)
                item["discovery_methods"] = [item.pop("discovery_method", "unknown")]
                merged[key] = item
    return sorted(merged.values(), key=lambda x: x.get("discovered_at", ""), reverse=True)


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    previous_payload = load_json(OUTPUT, {})
    previous = previous_payload.get("items", []) if isinstance(previous_payload, dict) else []
    state = load_json(STATE, {"runs": 0, "provider_rotation": 0})
    cc_items, cc_diag = search_commoncrawl()
    sx_items, sx_diag = search_searxng()
    fresh = cc_items + sx_items
    merged = merge_candidates(fresh, previous)
    diagnostics = cc_diag + sx_diag
    successful = sum(1 for row in diagnostics if row.get("status") == "ok")
    payload = {
        "schema_version": 1,
        "project": "OIO-SEARCH-ENGINE",
        "updated_at": now(),
        "total_candidates": len(merged),
        "new_candidates_this_run": len({x["url"] for x in fresh} - {x.get("url") for x in previous}),
        "items": merged,
        "provider_diagnostics": diagnostics,
        "notice": "Candidatos descobertos por índices públicos. Acesso, direitos e reprodução ainda precisam de validação; nenhum conteúdo foi baixado.",
    }
    save_json(OUTPUT, payload)
    state.update({
        "runs": int(state.get("runs", 0)) + 1,
        "last_run_at": now(),
        "last_new_candidates": payload["new_candidates_this_run"],
        "last_total_candidates": len(merged),
        "last_successful_provider_checks": successful,
        "provider_rotation": int(state.get("provider_rotation", 0)) + 1,
    })
    save_json(STATE, state)
    print(f"Novos candidatos: {payload['new_candidates_this_run']}")
    print(f"Total acumulado: {len(merged)}")
    print(f"Verificações de provedor concluídas: {successful}")
    print("Nenhum vídeo foi baixado; candidatos não são publicados como autorizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
