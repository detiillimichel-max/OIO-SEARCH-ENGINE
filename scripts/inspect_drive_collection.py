#!/usr/bin/env python3
"""Recursively inspect one public Google Drive collection and merge media into OIO discoveries."""
from __future__ import annotations
import json, os, re, time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/discovery-library.json"
SEED=os.getenv("DRIVE_TEST_FOLDER_ID","0B1lPp7clarJhNVRIdVBoNGdROHc").strip()
MAX_DEPTH=max(1,min(int(os.getenv("DRIVE_MAX_DEPTH","3")),5))
MAX_FOLDERS=max(1,min(int(os.getenv("DRIVE_MAX_FOLDERS","250")),500))
TIMEOUT=int(os.getenv("FOLDER_INSPECT_TIMEOUT","20"))
DELAY=float(os.getenv("FOLDER_INSPECT_DELAY","0.4"))
VIDEO={".mp4",".m4v",".mkv",".avi",".mov",".wmv",".webm",".mpg",".mpeg",".ts",".3gp"}
AUDIO={".mp3",".m4a",".aac",".ogg",".opus",".flac",".wav"}
UA="Mozilla/5.0 (compatible; OIO-SEARCH-ENGINE/1.3; +https://github.com/detiillimichel-max/OIO-SEARCH-ENGINE)"

class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.links=[]; self.anchor=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="a": self.anchor={"href":a.get("href",""),"text":a.get("aria-label") or a.get("title") or ""}
        if a.get("data-id"):
            self.links.append({"href":a.get("href",""),"text":a.get("aria-label") or a.get("data-tooltip") or a.get("title") or "", "data_id":a["data-id"]})
    def handle_data(self,data):
        if self.anchor is not None: self.anchor["text"]=(self.anchor["text"]+" "+data).strip()
    def handle_endtag(self,tag):
        if tag=="a" and self.anchor is not None:
            self.links.append(self.anchor); self.anchor=None

def item_id(href):
    if not href:return None
    u=urlparse(urljoin("https://drive.google.com/",href))
    m=re.search(r"/(?:drive/(?:u/\d+/)?|drive/mobile/)?folders/([A-Za-z0-9_-]+)",u.path)
    if m:return ("folder",m.group(1))
    m=re.search(r"/file/d/([A-Za-z0-9_-]+)",u.path)
    if m:return ("file",m.group(1))
    fid=parse_qs(u.query).get("id",[None])[0]
    if fid and ("folder" in u.path or "embeddedfolderview" in u.path):return ("folder",fid)
    if fid and ("open" in u.path or "uc" in u.path):return ("file",fid)
    return None

def inspect(folder_id,session):
    response=session.get("https://drive.google.com/embeddedfolderview",params={"id":folder_id},timeout=TIMEOUT)
    if response.status_code in (401,403): return None,[],[],f"HTTP {response.status_code}"
    response.raise_for_status()
    html=response.text
    if any(x in (html[:300000]+response.url).lower() for x in ("servicelogin","accounts.google.com","you need access","request access","access denied")):
        return None,[],[],"login_or_permission_wall"
    parser=Links(); parser.feed(html[:5_000_000])
    folders={}; files={}
    for entry in parser.links:
        found=("file",entry.get("data_id")) if entry.get("data_id") else item_id(entry.get("href"))
        name=re.sub(r"\s+"," ",entry.get("text","")).strip()
        if not found or not found[1] or not name: continue
        kind,fid=found; ext=Path(name.split("?")[0]).suffix.lower()
        if kind=="folder": folders[fid]={"id":fid,"name":name}
        elif ext in VIDEO|AUDIO:
            media="video" if ext in VIDEO else "audio"
            files[fid]={"id":fid,"name":name,"url":f"https://drive.google.com/file/d/{fid}/view","thumbnail":f"https://drive.google.com/thumbnail?id={fid}&sz=w640","media_type":media}
    title=re.search(r"<title[^>]*>(.*?)</title>",html,re.I|re.S)
    page_title=re.sub(r"\s+"," ",title.group(1)).strip() if title else ""
    return page_title,list(folders.values()),list(files.values()),"listed" if folders or files else "listing_unparsed"

def classify(path,files):
    text=(path+" "+" ".join(x["name"] for x in files)).lower()
    if any(x["media_type"]=="audio" for x in files): return "musicas"
    if any(w in text for w in ("desenho","cartoon","anime","samurai","thundercats","power rangers","she-ra","espias","espias")): return "desenhos_animacoes"
    if any(w in text for w in ("filme","movie","cinema","serie","série","temporada","episodio","episódio","jaspion","chaves")): return "filmes_series"
    return "videos"

def main():
    if not SEED: raise SystemExit("DRIVE_TEST_FOLDER_ID não informado")
    session=requests.Session(); session.headers.update({"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"})
    queue=[(SEED,"Desenhos",0)]; seen=set(); rows=[]; total_files=0; errors={}
    while queue and len(seen)<MAX_FOLDERS:
        fid,path,depth=queue.pop(0)
        if fid in seen: continue
        seen.add(fid)
        try:
            title,subfolders,files,status=inspect(fid,session)
            if status!="listed":
                errors[status]=errors.get(status,0)+1
            folder_title=path if not title or "google drive" in title.lower() else re.sub(r"\s*[-|]\s*Google Drive$","",title,flags=re.I).strip()
            category=classify(path,files)
            if files:
                for f in files:
                    f["category"]=category if f["media_type"]=="video" else "musicas"
                    f["folder_path"]=path
                    f["authorized"]=False
                    f["playback_ready"]=False
                rows.append({"id":fid,"url":f"https://drive.google.com/drive/folders/{fid}","title":folder_title,"folder_path":path,"depth":depth,"files":files,"counts":{"videos":sum(f["media_type"]=="video" for f in files),"audios":sum(f["media_type"]=="audio" for f in files)},"category":category,"included":True,"inspection_status":status,"verification_status":"page_reachable_unverified","evidence":"Listagem obtida sem OAuth; nomes e IDs visíveis no HTML público. Acesso/reprodução individual ainda não verificados."})
                total_files+=len(files)
            if depth<MAX_DEPTH:
                for child in subfolders:
                    if child["id"] not in seen:
                        queue.append((child["id"],path+" / "+child["name"],depth+1))
        except requests.RequestException as exc:
            errors["request_error"]=errors.get("request_error",0)+1
            rows.append({"id":fid,"title":path,"folder_path":path,"depth":depth,"files":[],"included":False,"inspection_status":"request_error","evidence":str(exc)[:240]})
        time.sleep(DELAY)
    existing={}
    if OUT.exists():
        try:
            payload=json.loads(OUT.read_text(encoding="utf-8"))
            for row in payload.get("items",[]): existing[row.get("id")]=row
        except Exception: pass
    # Keep the general discovery results, replacing only this explicit test collection by folder ID.
    for row in rows: existing[row["id"]]=row
    items=list(existing.values())
    result={"schema_version":4,"generated_at":datetime.now(timezone.utc).isoformat(),"test_collection":{"root_id":SEED,"root_url":f"https://drive.google.com/drive/folders/{SEED}","max_depth":MAX_DEPTH,"folders_visited":len(seen),"folders_with_media":sum(bool(x.get("files")) for x in rows),"media_files":total_files,"errors":errors},"folders_considered":len(items),"folders_with_media":sum(bool(x.get("files")) for x in items),"media_files":sum(len(x.get("files",[])) for x in items),"status_counts":errors,"categories":{"filmes_series":"Filmes e séries","desenhos_animacoes":"Desenhos e animações","musicas":"Músicas","videos":"Vídeos"},"items":items,"notice":"Descoberta recursiva de listagens públicas. Não usa cookies/OAuth, não baixa mídia, não contorna permissões e não declara autorização de reprodução."}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result["test_collection"],ensure_ascii=False,indent=2))
    print("Arquivos catalogados nesta coleção:",total_files)

if __name__=="__main__": main()
