const CATALOG_URL = "../data/drive-media.json";
const grid = document.getElementById("media-grid");
const searchInput = document.getElementById("search-input");
const statusEl = document.getElementById("catalog-status");
const countEl = document.getElementById("result-count");
const titleEl = document.getElementById("now-title");
const kindEl = document.getElementById("player-kind");
const frame = document.getElementById("player-frame");
const note = document.getElementById("player-note");
const nextButton = document.getElementById("next-btn");
let catalog = [];
let activeCategory = "todos";
let searchTerm = "";
let currentIndex = -1;

function safeUrl(value) {
  try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) ? u.href : null; }
  catch { return null; }
}
function driveFileId(value) {
  try {
    const u = new URL(value);
    if (!["drive.google.com", "docs.google.com"].includes(u.hostname)) return null;
    return u.pathname.match(/\/file\/d\/([a-zA-Z0-9_-]+)/)?.[1] || u.searchParams.get("id");
  } catch { return null; }
}
function playItem(index) {
  const item = catalog[index];
  if (!item) return;
  const url = safeUrl(item.url);
  if (!url) { note.textContent = "Este item não possui uma URL HTTP/HTTPS válida."; return; }
  currentIndex = index;
  titleEl.textContent = item.title || "Conteúdo selecionado";
  kindEl.textContent = (item.category || "MÍDIA").toUpperCase();
  nextButton.disabled = !catalog.some((x, i) => i !== index && x.category === item.category && x.series_id && x.series_id === item.series_id);
  frame.replaceChildren();
  const id = driveFileId(url);
  if (id) {
    const iframe = document.createElement("iframe");
    iframe.src = "https://drive.google.com/file/d/" + encodeURIComponent(id) + "/preview";
    iframe.title = item.title || "Pré-visualização Google Drive";
    iframe.allow = "autoplay; fullscreen; picture-in-picture";
    iframe.allowFullscreen = true;
    frame.appendChild(iframe);
    note.textContent = "Pré-visualização oficial do Drive. O acesso depende das permissões e da configuração de compartilhamento do arquivo.";
  } else if (item.playback_type === "direct" && item.authorized === true) {
    const video = document.createElement("video");
    video.controls = true; video.playsInline = true; video.preload = "metadata";
    video.src = url;
    const poster = safeUrl(item.poster); if (poster) video.poster = poster;
    frame.appendChild(video);
    note.textContent = "Reprodução direta de uma fonte identificada como autorizada. Compatibilidade depende do formato e do servidor.";
  } else {
    const link = document.createElement("a");
    link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
    link.className = "empty-player"; link.textContent = "Abrir fonte em nova aba";
    frame.appendChild(link);
    note.textContent = "Esta fonte não foi configurada para reprodução direta autorizada. Abrimos a origem sem tentar contornar restrições.";
  }
  document.querySelector(".player-section").scrollIntoView({behavior:"smooth",block:"start"});
}
function playNextEpisode() {
  if (currentIndex < 0) return;
  const current = catalog[currentIndex];
  const next = catalog.findIndex((item, i) => i > currentIndex && item.series_id && item.series_id === current.series_id);
  if (next >= 0) playItem(next);
  else { nextButton.disabled = true; note.textContent = "Não há outro episódio cadastrado para esta série."; }
}
function render() {
  const filtered = catalog.map((item,index)=>({item,index})).filter(({item})=>{
    const categoryOk = activeCategory === "todos" || item.category === activeCategory;
    const text = [item.title,item.description,item.category,...(item.tags||[])].join(" ").toLocaleLowerCase("pt-BR");
    return categoryOk && text.includes(searchTerm);
  });
  countEl.textContent = filtered.length + (filtered.length === 1 ? " título" : " títulos");
  grid.replaceChildren();
  if (!filtered.length) {
    const empty=document.createElement("div"); empty.className="empty-library";
    empty.textContent=catalog.length?"Nenhum resultado para este filtro.":"Catálogo vazio. Adicione itens autorizados em data/drive-media.json.";
    grid.appendChild(empty); return;
  }
  for (const {item,index} of filtered) {
    const card=document.createElement("article"); card.className="media-card"; card.tabIndex=0;
    const poster=safeUrl(item.poster);
    if (poster) { const img=document.createElement("img"); img.loading="lazy"; img.alt=""; img.src=poster; img.onerror=()=>img.remove(); card.appendChild(img); }
    else { const placeholder=document.createElement("div"); placeholder.className="poster-placeholder"; placeholder.textContent="▶"; card.appendChild(placeholder); }
    const info=document.createElement("div"); info.className="media-info";
    const h=document.createElement("h3"); h.textContent=item.title||"Sem título";
    const p=document.createElement("p"); p.textContent=[item.category||"Mídia",item.episode||item.year||""].filter(Boolean).join(" • ");
    info.append(h,p); card.appendChild(info);
    card.addEventListener("click",()=>playItem(index));
    card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();playItem(index);}});
    grid.appendChild(card);
  }
}
async function loadCatalog() {
  try {
    const response=await fetch(CATALOG_URL,{cache:"no-store"});
    if(!response.ok) throw new Error("HTTP "+response.status);
    const payload=await response.json();
    catalog=Array.isArray(payload)?payload:(Array.isArray(payload.items)?payload.items:[]);
    statusEl.textContent="Catálogo atualizado";
    render();
  } catch(error) {
    statusEl.textContent="Catálogo indisponível";
    grid.innerHTML='<div class="empty-library">Não foi possível carregar data/drive-media.json. Verifique o arquivo e tente novamente.</div>';
    console.error(error);
  }
}
searchInput.addEventListener("input",()=>{searchTerm=searchInput.value.trim().toLocaleLowerCase("pt-BR");render();});
document.querySelectorAll(".filter").forEach(button=>button.addEventListener("click",()=>{
  document.querySelectorAll(".filter").forEach(b=>b.classList.remove("active"));
  button.classList.add("active"); activeCategory=button.dataset.category; render();
}));
nextButton.addEventListener("click",playNextEpisode);
document.getElementById("fullscreen-btn").addEventListener("click",()=>{
  const target=frame.querySelector("iframe,video")||frame;
  if(target.requestFullscreen) target.requestFullscreen().catch(()=>{});
  else if(frame.requestFullscreen) frame.requestFullscreen().catch(()=>{});
});
loadCatalog();