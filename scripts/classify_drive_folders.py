#!/usr/bin/env python3
"""Inspect public Google Drive folder listings and keep media-only collections.

Uses Drive's public embedded-folder HTML view. It does not use private APIs,
OAuth tokens, permission bypasses, or download media files.
"""
from __future__ import annotations
import json, os, re, time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import requests

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
CANDIDATES=DATA/"discovery-candidates.json"
REPORT=DATA/"drive-verification-report.json"
OUTPUT=DATA/"discovery-library.json"
TIMEOUT=int(os.getenv("FOLDER_INSPECT_TIMEOUT","15"))
LIMIT=max(1,min(int(os.getenv("MAX_FOLDERS_TO_INSPECT","195")),250))
DELAY=float(os.getenv("FOLDER_INSPECT_DELAY","0.5"))
VIDEO={".mp4",".m4v",".mkv",".avi",".mov",".wmv",".webm",".mpg",".mpeg",".ts",".3gp"}
AUDIO={".mp3",".m4a",".aac",".ogg",".opus",".flac",".wav"}
IMAGE={".jpg",".jpeg",".png",".gif",".webp",".bmp"}
DOC={".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".txt",".rtf",".odt",".ods",".csv"}
UA="Mozilla/5.0 (compatible; OIO-SEARCH-ENGINE/1.0; +https://github.com/detiillimichel-max/OIO-SEARCH-ENGINE)"

class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.entries=[]; self.current=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="div" and (a.get("class","").find("flip-entry")>=0 or a.get("data-id")):
            self.current={"name":a.get("aria-label") or a.get("data-tooltip") or a.get("title") or "", "id":a.get("data-id"),"href":""}
            self.entries.append(self.current)
        elif tag=="a" and self.current is not None:
            self.current["href"]=a.get("href","")
            if a.get("aria-label"): self.current["name"]=a["aria-label"]
    def handle_data(self,data):
        if self.current is not None and data.strip():
            self.current["name"]=(self.current.get("name","")+" "+data.strip()).strip()[:500]
    def handle_endtag(self,tag):
        if tag=="div" and self.current is not None: self.current=None

def classify_name(name):
    n=(name or "").lower()
    ext=Path(n.split("?")[0]).suffix.lower()
    if ext in VIDEO: return "videos"
    if ext in AUDIO: return "musicas"
    if ext in DOC or ext in IMAGE: return "documentos_outros"
    if any(x in n for x in ("temporada","episodio","episode","season","série","serie")): return "filmes_series"
    if any(x in n for x in ("desenho","animacao","animação","cartoon","anime")): return "desenhos_animacoes"
    return "outros"

def main():
    candidates=json.loads(CANDIDATES.read_text(encoding="utf-8")).get("items",[])
    checks=json.loads(REPORT.read_text(encoding="utf-8")).get("items",[])
    check_by_id={x.get("id"):x for x in checks}
    folders=[x for x in candidates if x.get("kind")=="folder"][:LIMIT]
    output=[]; diagnostics={}
    session=requests.Session(); session.headers.update({"User-Agent":UA})
    for folder in folders:
        check=check_by_id.get(folder.get("id"),{})
        status=check.get("verification_status","unknown")
        row={"id":folder.get("id"),"url":folder.get("url"),"title":folder.get("title") or "Pasta do Google Drive","verification_status":status,"files":[],"counts":{},"category":None,"included":False,"inspection_status":"not_inspected","evidence":""}
        if status not in ("page_reachable_unverified",):
            row["inspection_status"]="skipped_not_reachable"
            row["evidence"]="A verificação anterior não indicou uma página HTML acessível."
            output.append(row); diagnostics[row["inspection_status"]]=diagnostics.get(row["inspection_status"],0)+1; continue
        try:
            response=session.get("https://drive.google.com/embeddedfolderview",params={"id":folder["id"]},timeout=TIMEOUT)
            if response.status_code in (401,403): raise PermissionError("A pasta exige permissão.")
            response.raise_for_status()
            parser=ListingParser(); parser.feed(response.text[:2_000_000])
            # Also extract conventional Drive file links when the embedded markup uses anchors.
            found={}
            for entry in parser.entries:
                name=re.sub(r"\s+"," ",entry.get("name","")).strip()
                href=entry.get("href","")
                fid=entry.get("id")
                if not fid and href:
                    m=re.search(r"/file/d/([A-Za-z0-9_-]+)",href); fid=m.group(1) if m else None
                if name and fid: found[fid]={"id":fid,"name":name,"url":"https://drive.google.com/file/d/"+fid+"/view","category":classify_name(name)}
            row["files"]=list(found.values())
            counts={}
            for f in row["files"]: counts[f["category"]]=counts.get(f["category"],0)+1
            row["counts"]=counts
            media=[f for f in row["files"] if f["category"] in ("videos","musicas","filmes_series","desenhos_animacoes")]
            row["files"]=media
            row["included"]=bool(media)
            row["category"]=("videos" if counts.get("videos") else "filmes_series" if counts.get("filmes_series") else "desenhos_animacoes" if counts.get("desenhos_animacoes") else "musicas" if counts.get("musicas") else None)
            row["inspection_status"]="listed" if found else "listing_empty_or_markup_changed"
            row["evidence"]="Itens identificados na listagem pública; documentos e outros tipos foram excluídos do catálogo."
        except PermissionError as exc:
            row["inspection_status"]="restricted"; row["evidence"]=str(exc)
        except requests.RequestException as exc:
            row["inspection_status"]="request_error"; row["evidence"]=str(exc)[:240]
        except Exception as exc:
            row["inspection_status"]="inspection_error"; row["evidence"]=str(exc)[:240]
        output.append(row); diagnostics[row["inspection_status"]]=diagnostics.get(row["inspection_status"],0)+1
        time.sleep(DELAY)
    result={"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"folders_considered":len(folders),"folders_with_media":sum(x["included"] for x in output),"media_files":sum(len(x["files"]) for x in output),"status_counts":diagnostics,"categories":{"videos":"Pastas com vídeos","filmes_series":"Filmes e séries","desenhos_animacoes":"Desenhos e animações","musicas":"Músicas"},"excluded":"Pastas contendo somente documentos, imagens ou outros tipos não multimídia não entram no catálogo.","items":[x for x in output if x["included"]]}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="items"},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
