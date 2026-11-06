#!/usr/bin/env python3
"""Gera consultas Google Dorks para localizar links do Drive publicamente indexados.

Este módulo monta consultas e URLs para abrir no Google. Não raspa páginas
de resultados, não acessa arquivos privados e não baixa conteúdo.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

OUTPUT = Path("data/google-dorks-catalog.json")

CATEGORIES = {
    "videos": ["vídeos", "video", "clipes"],
    "filmes": ["filme", "filmes", "longa-metragem"],
    "series": ["série", "episódio", "temporada"],
    "desenhos": ["desenho", "animação", "cartoon"],
    "documentarios": ["documentário", "documentários", "documental"],
}

EXTENSIONS = ["mp4", "mkv", "avi", "mov", "webm", "m4v"]


def build_queries(category: str, term: str | None) -> list[dict]:
    selected = CATEGORIES if category == "todos" else {category: CATEGORIES[category]}
    queries: list[dict] = []

    for category_name, keywords in selected.items():
        for keyword in keywords:
            phrase = f'"{keyword}"'
            queries.append({
                "category": category_name,
                "kind": "drive_file",
                "query": f"site:drive.google.com/file/d/ {phrase}",
            })
            queries.append({
                "category": category_name,
                "kind": "drive_folder",
                "query": f"site:drive.google.com/drive/folders {phrase}",
            })

        for extension in EXTENSIONS:
            queries.append({
                "category": category_name,
                "kind": "extension_hint",
                "query": f'site:drive.google.com "{extension}"',
            })

    if term:
        safe_term = " ".join(term.split())
        queries.insert(0, {
            "category": "personalizada",
            "kind": "custom_term",
            "query": f'site:drive.google.com "{safe_term}"',
        })
        for extension in EXTENSIONS:
            queries.append({
                "category": "personalizada",
                "kind": "custom_term_extension",
                "query": f'site:drive.google.com "{safe_term}" "{extension}"',
            })

    # Deduplica mantendo a ordem.
    seen: set[str] = set()
    unique: list[dict] = []
    for item in queries:
        query = item["query"]
        if query in seen:
            continue
        seen.add(query)
        item["google_url"] = "https://www.google.com/search?q=" + quote_plus(query)
        unique.append(item)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera Google Dorks para Drive público indexado.")
    parser.add_argument("--category", choices=[*CATEGORIES, "todos"], default="todos")
    parser.add_argument("--term", default="", help="Título, nome ou assunto para pesquisar.")
    args = parser.parse_args()

    queries = build_queries(args.category, args.term.strip() or None)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "OIO-SEARCH-ENGINE",
        "module": "google-dorks-drive",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "category": args.category,
        "custom_term": args.term.strip() or None,
        "total_queries": len(queries),
        "queries": queries,
        "limitations": [
            "As consultas mostram somente páginas que o Google decidiu indexar.",
            "Um resultado não garante que o arquivo exista, esteja público ou possa ser reproduzido.",
            "O Google pode ignorar operadores ou variar os resultados.",
            "Este módulo gera links de pesquisa; não coleta nem baixa resultados automaticamente.",
            "Use apenas arquivos que você tenha autorização para acessar e utilizar.",
        ],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Consultas geradas: {len(queries)}")
    print(f"Catálogo: {OUTPUT}")


if __name__ == "__main__":
    main()
