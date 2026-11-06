#!/usr/bin/env python3
"""Publica lotes programados a partir de um acervo autorizado.

Este motor agenda conteúdos reais do content-pool.json. Ele não cria contas,
curtidas, comentários ou identidades fictícias.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POOL_FILE = DATA / "content-pool.json"
QUEUE_FILE = DATA / "publication-queue.json"
HISTORY_FILE = DATA / "publication-history.json"
FEED_FILE = DATA / "social-feed.json"
REPORT_FILE = DATA / "auto-publish-report.json"
TZ = ZoneInfo(os.getenv("PUBLISH_TIMEZONE", "America/Sao_Paulo"))
BATCH_PATTERN = [100, 50, 70, 120, 80, 100]
ALLOWED_CATEGORIES = {"videos", "filmes", "series", "desenhos", "documentarios", "jornalismo", "educacao"}


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def valid_item(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("id", "title", "url", "category")):
        return False
    if item["category"] not in ALLOWED_CATEGORIES:
        return False
    if item.get("authorized") is not True or item.get("status", "ready") != "ready":
        return False
    return item["url"].startswith("https://")


def main() -> None:
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(TZ)
    # Um lote por janela de dez minutos; o tamanho varia conforme o ciclo.
    slot = (local_now.hour * 60 + local_now.minute) // 10
    batch_size = BATCH_PATTERN[slot % len(BATCH_PATTERN)]

    pool_payload = read_json(POOL_FILE, {"items": []})
    queue_payload = read_json(QUEUE_FILE, {"items": []})
    history_payload = read_json(HISTORY_FILE, {"published_ids": []})
    feed_payload = read_json(FEED_FILE, {"items": []})

    pool = pool_payload.get("items", []) if isinstance(pool_payload, dict) else []
    queued = queue_payload.get("items", []) if isinstance(queue_payload, dict) else []
    history = history_payload.get("published_ids", []) if isinstance(history_payload, dict) else []
    feed = feed_payload.get("items", []) if isinstance(feed_payload, dict) else []

    # A fila tem prioridade; o acervo é usado para completar o lote.
    candidates = queued + pool
    seen = set(history)
    batch = []
    for item in candidates:
        if not valid_item(item) or item["id"] in seen:
            continue
        seen.add(item["id"])
        published = dict(item)
        published["published_at"] = now.isoformat()
        published["publication_source"] = "oio-auto-publish-engine"
        batch.append(published)
        if len(batch) >= batch_size:
            break

    # Feed recente primeiro; limita o JSON público para manter o download leve.
    merged = batch + feed
    deduped = []
    feed_seen = set()
    for item in merged:
        item_id = item.get("id")
        if item_id and item_id not in feed_seen:
            feed_seen.add(item_id)
            deduped.append(item)
    deduped = deduped[:10000]

    new_ids = [item["id"] for item in batch]
    # Só altera os arquivos públicos quando houver publicações novas.
    # Isso evita um commit vazio/ruidoso a cada execução agendada.
    remaining_queue = [x for x in queued if isinstance(x, dict) and x.get("id") not in set(new_ids)]
    if batch:
        write_json(FEED_FILE, {
            "schema_version": 1,
            "updated_at": now.isoformat(),
            "timezone": str(TZ),
            "items": deduped
        })
        write_json(HISTORY_FILE, {
            "updated_at": now.isoformat(),
            "published_ids": (history + new_ids)[-50000:]
        })
        write_json(QUEUE_FILE, {"updated_at": now.isoformat(), "items": remaining_queue})
    report = {
        "ran_at_utc": now.isoformat(),
        "ran_at_local": local_now.isoformat(),
        "requested_batch_size": batch_size,
        "published_count": len(batch),
        "remaining_queue_count": len(remaining_queue),
        "feed_count": len(deduped),
        "message": "Nenhum conteúdo novo elegível." if not batch else "Lote publicado no catálogo."
    }
    write_json(REPORT_FILE, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
