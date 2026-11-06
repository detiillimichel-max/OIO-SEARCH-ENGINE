#!/usr/bin/env python3
import json, re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "drive.json"
OUTPUT = ROOT / "data" / "catalog.json"
URL_RE = re.compile(r"^https?://drive\.google\.com/", re.I)
ID_RE = re.compile(r"/file/d/([^/?]+)", re.I)

def main():
    if not SOURCE.exists():
        raise SystemExit(f"Origem não encontrada: {SOURCE}")
    seen, items, pending = set(), [], ""
    for raw in SOURCE.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("site:"):
            continue
        if URL_RE.match(line):
            match = ID_RE.search(line)
            if match:
                file_id = match.group(1)
                if file_id not in seen:
                    seen.add(file_id)
                    items.append({
                        "id": file_id,
                        "title": pending or f"Vídeo {len(items) + 1}",
                        "url": line,
                        "embed_url": f"https://drive.google.com/file/d/{file_id}/preview"
                    })
            pending = ""
        else:
            pending = line

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "title": "Minha TV",
        "source": "docs/drive.json",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(items),
        "items": items
    }
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catálogo gerado: {len(items)} arquivos únicos")

if __name__ == "__main__":
    main()
