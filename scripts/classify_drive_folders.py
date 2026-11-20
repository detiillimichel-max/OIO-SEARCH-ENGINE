#!/usr/bin/env python3
"""Inspect public Google Drive folder listings and keep media-only collections.

Only reads public HTML metadata. It never uses OAuth, bypasses permissions,
or downloads media content.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CANDIDATES = DATA / "discovery-candidates.json"
REPORT = DATA / "drive-verification-report.json"
OUTPUT = DATA / "discovery-library.json"
TIMEOUT = int(os.getenv("FOLDER_INSPECT_TIMEOUT", "15"))
LIMIT = max(1, min(int(os.getenv("MAX_FOLDERS_TO_INSPECT", "195")), 250))
DELAY = float(os.getenv("FOLDER_INSPECT_DELAY", "0.5"))
VIDEO = {".mp4", ".m4v", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".mpg", ".mpeg", ".ts", ".3gp"}
AUDIO = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
DOC = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt", ".ods", ".csv"}
UA = "Mozilla/5.0 (compatible; OIO-SEARCH-ENGINE/1.1; +https://github.com/detiillimichel-max/OIO-SEARCH-ENGINE)"


class ListingParser(HTMLParser):
    """Extract Drive file links without assuming a fixed nesting depth."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries = []
        self.anchors = []
        self.stack = []
        self.current_entry = None
        self.current_entry_depth = None
        self.current_anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.stack.append(tag)
        if tag == "div" and (
            "flip-entry" in (attrs.get("class") or "")
            or attrs.get("data-id")
        ):
            entry = {
                "name": attrs.get("aria-label") or attrs.get("data-tooltip")
                        or attrs.get("title") or "",
                "id": attrs.get("data-id"),
                "href": "",
            }
            self.entries.append(entry)
            self.current_entry = entry
            self.current_entry_depth = len(self.stack)
        if tag == "a":
            self.current_anchor = {
                "href": attrs.get("href", ""),
                "name": attrs.get("aria-label") or attrs.get("title") or "",
            }

    def handle_data(self, data):
        value = data.strip()
        if not value:
            return
        if self.current_entry is not None:
            self.current_entry["name"] = (
                self.current_entry.get("name", "") + " " + value
            ).strip()[:500]
        if self.current_anchor is not None:
            self.current_anchor["name"] = (
                self.current_anchor.get("name", "") + " " + value
            ).strip()[:500]

    def handle_endtag(self, tag):
        if tag == "a" and self.current_anchor is not None:
            self.anchors.append(self.current_anchor)
            if self.current_entry is not None and not self.current_entry.get("href"):
                self.current_entry["href"] = self.current_anchor.get("href", "")
            self.current_anchor = None

        # Close an entry only when its own opening DIV is closed. Nested DIVs
        # must not terminate the parent entry (the old parser did this).
        if (
            tag == "div"
            and self.current_entry is not None
            and self.current_entry_depth == len(self.stack)
        ):
            self.current_entry = None
            self.current_entry_depth = None

        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index] == tag:
                del self.stack[index:]
                break


def file_id_from_url(href):
    if not href:
        return None
    absolute = urljoin("https://drive.google.com/", href)
    parsed = urlparse(absolute)
    match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
    if match:
        return match.group(1)
    if parsed.path.endswith("/open") or parsed.path.endswith("/uc"):
        return parse_qs(parsed.query).get("id", [None])[0]
    return None


def classify_name(name):
    normalized = (name or "").lower()
    extension = Path(normalized.split("?")[0]).suffix.lower()
    if extension in VIDEO:
        return "videos"
    if extension in AUDIO:
        return "musicas"
    if extension in DOC or extension in IMAGE:
        return "documentos_outros"
    if any(word in normalized for word in ("temporada", "episodio", "episode", "season", "série", "serie")):
        return "filmes_series"
    if any(word in normalized for word in ("desenho", "animacao", "animação", "cartoon", "anime")):
        return "desenhos_animacoes"
    return "outros"


def extract_files(html):
    parser = ListingParser()
    parser.feed(html[:5_000_000])
    found = {}

    # Anchor extraction is independent of Drive's changing DIV/class markup.
    for item in parser.anchors:
        fid = file_id_from_url(item.get("href"))
        name = re.sub(r"\s+", " ", item.get("name", "")).strip()
        if fid and name:
            found[fid] = {
                "id": fid,
                "name": name,
                "url": f"https://drive.google.com/file/d/{fid}/view",
                "category": classify_name(name),
            }

    # Some embedded views expose the file ID on a container instead of its link.
    for item in parser.entries:
        fid = item.get("id") or file_id_from_url(item.get("href"))
        name = re.sub(r"\s+", " ", item.get("name", "")).strip()
        if fid and name:
            found.setdefault(fid, {
                "id": fid,
                "name": name,
                "url": f"https://drive.google.com/file/d/{fid}/view",
                "category": classify_name(name),
            })
    return list(found.values())


def page_is_login_or_blocked(html, final_url):
    sample = (html[:250_000] + " " + final_url).lower()
    markers = (
        "servicelogin", "accounts.google.com", "sign in - google accounts",
        "you need access", "request access", "access denied",
    )
    return any(marker in sample for marker in markers)


def main():
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8")).get("items", [])
    checks = json.loads(REPORT.read_text(encoding="utf-8")).get("items", [])
    check_by_id = {item.get("id"): item for item in checks}
    folders = [item for item in candidates if item.get("kind") == "folder"][:LIMIT]
    output = []
    diagnostics = {}
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})

    for folder in folders:
        check = check_by_id.get(folder.get("id"), {})
        status = check.get("verification_status", "unknown")
        row = {
            "id": folder.get("id"),
            "url": folder.get("url"),
            "title": folder.get("title") or "Pasta do Google Drive",
            "verification_status": status,
            "files": [],
            "counts": {},
            "category": None,
            "included": False,
            "inspection_status": "not_inspected",
            "evidence": "",
        }
        if status != "page_reachable_unverified":
            row["inspection_status"] = "skipped_not_reachable"
            row["evidence"] = "A verificação anterior não indicou uma página HTML acessível."
            output.append(row)
            diagnostics[row["inspection_status"]] = diagnostics.get(row["inspection_status"], 0) + 1
            continue

        try:
            response = session.get(
                "https://drive.google.com/embeddedfolderview",
                params={"id": folder["id"]},
                timeout=TIMEOUT,
            )
            if response.status_code in (401, 403):
                row["inspection_status"] = "restricted"
                row["evidence"] = f"Servidor respondeu HTTP {response.status_code}."
            else:
                response.raise_for_status()
                html = response.text
                if page_is_login_or_blocked(html, response.url):
                    row["inspection_status"] = "login_or_access_wall"
                    row["evidence"] = "A página retornada solicita login ou acesso."
                else:
                    all_files = extract_files(html)
                    media = [
                        item for item in all_files
                        if item["category"] in ("videos", "musicas", "filmes_series", "desenhos_animacoes")
                    ]
                    counts = {}
                    for item in all_files:
                        counts[item["category"]] = counts.get(item["category"], 0) + 1
                    row["files"] = media
                    row["counts"] = counts
                    row["included"] = bool(media)
                    row["category"] = (
                        "videos" if counts.get("videos")
                        else "filmes_series" if counts.get("filmes_series")
                        else "desenhos_animacoes" if counts.get("desenhos_animacoes")
                        else "musicas" if counts.get("musicas")
                        else None
                    )
                    row["inspection_status"] = "listed" if all_files else "listing_unparsed"
                    row["evidence"] = (
                        "Nomes e IDs extraídos da listagem HTML pública; itens não multimídia foram excluídos."
                        if all_files else
                        f"HTML recebido ({len(html)} caracteres), mas nenhum link de arquivo reconhecível foi encontrado."
                    )
        except requests.RequestException as exc:
            row["inspection_status"] = "request_error"
            row["evidence"] = str(exc)[:240]
        except Exception as exc:
            row["inspection_status"] = "inspection_error"
            row["evidence"] = str(exc)[:240]

        output.append(row)
        diagnostics[row["inspection_status"]] = diagnostics.get(row["inspection_status"], 0) + 1
        time.sleep(DELAY)

    result = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "folders_considered": len(folders),
        "folders_with_media": sum(item["included"] for item in output),
        "media_files": sum(len(item["files"]) for item in output),
        "status_counts": diagnostics,
        "categories": {
            "videos": "Pastas com vídeos",
            "filmes_series": "Filmes e séries",
            "desenhos_animacoes": "Desenhos e animações",
            "musicas": "Músicas",
        },
        "excluded": "Pastas contendo somente documentos, imagens ou outros tipos não multimídia não entram no catálogo.",
        "items": [item for item in output if item["included"]],
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "items"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
