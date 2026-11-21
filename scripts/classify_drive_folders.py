#!/usr/bin/env python3
"""Classify public Drive folder media using folder + file names.

No OAuth, permission bypass, paid API, or media download is used.
"""
from __future__ import annotations
import json, os, re, time
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
LIMIT = max(1, min(int(os.getenv("MAX_FOLDERS_TO_INSPECT", "250")), 500))
DELAY = float(os.getenv("FOLDER_INSPECT_DELAY", "0.5"))
VIDEO = {".mp4",".m4v",".mkv",".avi",".mov",".wmv",".webm",".mpg",".mpeg",".ts",".3gp"}
AUDIO = {".mp3",".m4a",".aac",".ogg",".opus",".flac",".wav"}
IMAGE = {".jpg",".jpeg",".png",".gif",".webp",".bmp"}
DOC = {".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".txt",".rtf",".odt",".ods",".csv"}
UA = "Mozilla/5.0 (compatible; OIO-SEARCH-ENGINE/1.2; +https://github.com/detiillimichel-max/OIO-SEARCH-ENGINE)"

# Strong context terms only: generic words such as "video", "file" and "download"
# never make a folder entertainment by themselves.
TERMS = {
 "filmes_series": ["filme","filmes","movie","movies","cinema","longa","longas","serie","series","série","séries","temporada","season","episodio","episódio","episodes","tv show","novela","novelas","documentario","documentário"],
 "desenhos_animacoes": ["desenho","desenhos","animacao","animação","animacoes","animações","cartoon","cartoons","anime","animes","animê","pixar","disney","dreamworks"],
 "musicas": ["musica","música","musicas","músicas","album","álbum","discografia","soundtrack","trilha sonora","playlist","audio","áudio","mp3"]
}
def norm(value):
    value = (value or "").lower()
    value = value.replace("ç","c").replace("ã","a").replace("á","a").replace("à","a").replace("â","a").replace("é","e").replace("ê","e").replace("í","i").replace("ó","o").replace("ô","o").replace("õ","o").replace("ú","u")
    return re.sub(r"\s+"," ",value).strip()

def term_score(text, terms):
    value = norm(text)
    return sum(1 for term in terms if norm(term) in value)

class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries=[]; self.anchors=[]; self.stack=[]
        self.current_entry=None; self.current_depth=None; self.current_anchor=None
        self.in_title=False; self.page_title=""
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); self.stack.append(tag)
        if tag=="title": self.in_title=True
        if tag=="div" and ("flip-entry" in (a.get("class") or "") or a.get("data-id")):
            e={"name":a.get("aria-label") or a.get("data-tooltip") or a.get("title") or "", "id":a.get("data-id"),"href":""}
            self.entries.append(e); self.current_entry=e; self.current_depth=len(self.stack)
        if tag=="a":
            self.current_anchor={"href":a.get("href",""),"name":a.get("aria-label") or a.get("title") or ""}
    def handle_data(self,data):
        v=data.strip()
        if not v:return
        if self.in_title:self.page_title=(self.page_title+" "+v).strip()[:500]
        if self.current_entry is not None:self.current_entry["name"]=(self.current_entry.get("name","")+" "+v).strip()[:500]
        if self.current_anchor is not None:self.current_anchor["name"]=(self.current_anchor.get("name","")+" "+v).strip()[:500]
    def handle_endtag(self,tag):
        if tag=="title":self.in_title=False
        if tag=="a" and self.current_anchor is not None:
            self.anchors.append(self.current_anchor)
            if self.current_entry is not None and not self.current_entry.get("href"):self.current_entry["href"]=self.current_anchor.get("href","")
            self.current_anchor=None
        if tag=="div" and self.current_entry is not None and self.current_depth==len(self.stack):
            self.current_entry=None; self.current_depth=None
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i]==tag:del self.stack[i:];break

def file_id_from_url(href):
    if not href:return None
    p=urlparse(urljoin("https://drive.google.com/",href))
    m=re.search(r"/file/d/([A-Za-z0-9_-]+)",p.path)
    if m:return m.group(1)
    if p.path.endswith("/open") or p.path.endswith("/uc"):return parse_qs(p.query).get("id",[None])[0]
    return None

def extract_files(html):
    parser=ListingParser(); parser.feed(html[:5_000_000]); found={}
    for item in parser.anchors+parser.entries:
        fid=item.get("id") or file_id_from_url(item.get("href"))
        name=re.sub(r"\s+"," ",item.get("name","")).strip()
        if not fid or not name:continue
        ext=Path(name.split("?")[0]).suffix.lower()
        if ext in VIDEO:kind="video"
        elif ext in AUDIO:kind="audio"
        elif ext in DOC or ext in IMAGE:kind="other"
        else:continue
        found[fid]={"id":fid,"name":name,"url":f"https://drive.google.com/file/d/{fid}/view","media_type":kind}
    return parser.page_title,list(found.values())

def classify_collection(folder_name, files):
    context=" ".join([folder_name]+[f["name"] for f in files])
    # Explicit folder context has priority over generic filenames such as
    # "episodio-01", which can occur in both cartoons and live-action series.
    folder_scores={k:term_score(folder_name,v) for k,v in TERMS.items()}
    folder_best=max(folder_scores,key=folder_scores.get) if folder_scores else None
    if folder_best and folder_scores[folder_best]>0:
        return folder_best,"entertainment","folder_name_context"
    # Audio files are music by media type; video collections need explicit context.
    if any(f["media_type"]=="audio" for f in files) and term_score(context,TERMS["musicas"]):
        return "musicas","entertainment", "music_context"
    scores={k:term_score(context,v) for k,v in TERMS.items() if k!="musicas"}
    best=max(scores,key=scores.get) if scores else None
    if best and scores[best]>0:return best,"entertainment", "name_context"
    if any(f["media_type"]=="audio" for f in files):return "musicas","entertainment","audio_extension"
    if any(f["media_type"]=="video" for f in files):return "videos_diversos","misc","no_entertainment_context"
    return None,"excluded","no_media"

def main():
    candidates=json.loads(CANDIDATES.read_text(encoding="utf-8")).get("items",[])
    checks=json.loads(REPORT.read_text(encoding="utf-8")).get("items",[])
    check_by_id={x.get("id"):x for x in checks}
    folders=[x for x in candidates if x.get("kind")=="folder"][:LIMIT]
    entertainment=[]; misc=[]; diagnostics={}
    session=requests.Session();session.headers.update({"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"})
    for folder in folders:
        status=check_by_id.get(folder.get("id"),{}).get("verification_status","unknown")
        row={"id":folder.get("id"),"url":folder.get("url"),"title":folder.get("title") or "Pasta do Google Drive","verification_status":status,"files":[],"counts":{},"category":None,"classification":"pending","inspection_status":"not_inspected","evidence":""}
        if status!="page_reachable_unverified":
            row["inspection_status"]="skipped_not_reachable";row["evidence"]="A verificação anterior não indicou página HTML acessível."
        else:
            try:
                response=session.get("https://drive.google.com/embeddedfolderview",params={"id":folder["id"]},timeout=TIMEOUT)
                if response.status_code in (401,403):
                    row["inspection_status"]="restricted";row["evidence"]=f"HTTP {response.status_code}."
                else:
                    response.raise_for_status()
                    html=response.text
                    sample=(html[:250000]+" "+response.url).lower()
                    if any(x in sample for x in ("servicelogin","accounts.google.com","you need access","request access","access denied")):
                        row["inspection_status"]="login_or_access_wall";row["evidence"]="A página solicita login ou acesso."
                    else:
                        page_title,files=extract_files(html)
                        if page_title and row["title"]=="Pasta do Google Drive":
                            row["title"]=re.sub(r"\s*[-|]\s*Google Drive$","",page_title,flags=re.I).strip() or row["title"]
                        media=[f for f in files if f["media_type"] in ("video","audio")]
                        row["counts"]={"videos":sum(f["media_type"]=="video" for f in files),"audios":sum(f["media_type"]=="audio" for f in files),"outros_ignorados":0}
                        row["inspection_status"]="listed" if files else "listing_unparsed"
                        row["files"]=media
                        if files:row["category"],row["classification"],reason=classify_collection(row["title"],media)
                        else:reason="listing_unparsed"
                        row["classification_reason"]=reason if files else reason
                        row["included"]=bool(media)
                        row["evidence"]="Classificação baseada no nome da pasta e nos nomes dos arquivos; documentos/imagens não são publicados." if files else f"HTML recebido ({len(html)} caracteres), sem arquivos reconhecíveis."
            except requests.RequestException as exc:
                row["inspection_status"]="request_error";row["evidence"]=str(exc)[:240]
            except Exception as exc:
                row["inspection_status"]="inspection_error";row["evidence"]=str(exc)[:240]
        diagnostics[row["inspection_status"]]=diagnostics.get(row["inspection_status"],0)+1
        if row.get("included"):
            if row["classification"]=="entertainment":
                for f in row["files"]:
                    if f["media_type"]=="video" and row["category"] in ("filmes_series","desenhos_animacoes"):f["category"]=row["category"]
                    elif f["media_type"]=="audio":f["category"]="musicas"
                    else:f["category"]="videos"
                entertainment.append(row)
            elif row["classification"]=="misc":
                for f in row["files"]:f["category"]="videos_diversos" if f["media_type"]=="video" else "musicas"
                misc.append(row)
        time.sleep(DELAY)
    result={"schema_version":3,"generated_at":datetime.now(timezone.utc).isoformat(),"folders_considered":len(folders),"folders_with_media":len(entertainment)+len(misc),"entertainment_folders":len(entertainment),"entertainment_files":sum(len(x["files"]) for x in entertainment),"misc_folders":len(misc),"misc_files":sum(len(x["files"]) for x in misc),"status_counts":diagnostics,"categories":{"filmes_series":"Filmes e séries","desenhos_animacoes":"Desenhos e animações","musicas":"Músicas","videos":"Vídeos associados a conteúdo de entretenimento","videos_diversos":"Vídeos diversos — fora da biblioteca principal"},"items":entertainment,"misc_items":misc,"notice":"A descoberta usa somente listagens públicas; não contorna permissões nem baixa mídia. A classificação é heurística e pode exigir revisão."}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("items","misc_items")},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
