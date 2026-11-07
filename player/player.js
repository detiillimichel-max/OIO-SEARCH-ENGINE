const CATALOG_URL = "../data/catalog.json";
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
let currentDriveUrl = "";
let driveStarted = false;

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
function showDriveFallback(url, label = "Abrir no Google Drive") {
  const link = document.createElement("a");
  link.className = "drive-fallback";
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = label;
  return link;
}
function startDrivePlayback(id, title) {
  const iframe = frame.querySelector("iframe");
  if (!iframe || !id) return;
  driveStarted = true;
  // Aciona tela cheia diretamente no gesto do usuário, antes de navegar o iframe.
  const fullscreenTarget = frame;
  let fullscreenRequest = null;
  if (fullscreenTarget.requestFullscreen) {
    try { fullscreenRequest = fullscreenTarget.requestFullscreen(); } catch (_) {}
  }
  iframe.src = "https://drive.google.com/file/d/" + encodeURIComponent(id) + "/preview?autoplay=1";
  const action = frame.querySelector(".preview-action");
  if (action) action.remove();
  if (fullscreenRequest && typeof fullscreenRequest.catch === "function") fullscreenRequest.catch(() => {});
  note.textContent = "Reprodução solicitada. Se o navegador não permitir tela cheia automática, use o botão Tela cheia. Para qualquer falha, abra no Google Drive.";
}
function playItem(index) {
  const item = catalog[index];
  if (!item) return;
  const url = safeUrl(item.url);
  if (!url) { note.textContent = "Este item não possui uma URL HTTP/HTTPS válida."; return; }
  currentIndex = index;
  currentDriveUrl = url;
  driveStarted = false;
  titleEl.textContent = item.title || "Conteúdo selecionado";
  kindEl.textContent = (item.category || "FILMES").toUpperCase();
  nextButton.disabled = index >= catalog.length - 1;
  frame.replaceChildren();
  const id = driveFileId(url);
  if (id) {
    const iframe = document.createElement("iframe");
    iframe.src = "https://drive.google.com/file/d/" + encodeURIComponent(id) + "/preview";
    iframe.title = item.title || "Pré-visualização Google Drive";
    iframe.allow = "autoplay; fullscreen; picture-in-picture";
    iframe.allowFullscreen = true;
    iframe.referrerPolicy = "no-referrer";
    frame.appendChild(iframe);

    const overlay = document.createElement("div");
    overlay.className = "preview-action";
    const play = document.createElement("button");
    play.type = "button";
    play.className = "preview-play";
    play.innerHTML = '<span aria-hidden="true">▶</span><b>Reproduzir</b>';
    play.addEventListener("click", () => startDrivePlayback(id, item.title));
    overlay.appendChild(play);
    frame.appendChild(overlay);
    frame.appendChild(showDriveFallback(url));
    note.textContent = "Prévia oficial do Drive. Toque em Reproduzir para solicitar o início; a autorização e a compatibilidade são controladas pelo Drive.";
  } else if (item.playback_type === "direct" && item.authorized === true) {
    const video = document.createElement("video");
    video.controls = true; video.playsInline = true; video.preload = "metadata";
    video.src = url;
    const poster = safeUrl(item.poster); if (poster) video.poster = poster;
    frame.appendChild(video);
    frame.appendChild(showDriveFallback(url, "Abrir fonte"));
    note.textContent = "Reprodução direta de uma fonte identificada como autorizada.";
  } else {
    const link = showDriveFallback(url, "Abrir fonte em nova aba");
    frame.appendChild(link);
    note.textContent = "Esta fonte não foi configurada para reprodução direta autorizada.";
  }
  document.querySelector(".player-section").scrollIntoView({behavior:"smooth",block:"start"});
}
function playNextEpisode() {
  if (currentIndex < 0 || currentIndex >= catalog.length - 1) return;
  playItem(currentIndex + 1);
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
    empty.textContent=catalog.length?"Nenhum resultado para este filtro.":"O catálogo carregou, mas não contém itens.";
    grid.appendChild(empty); return;
  }
  for (const {item,index} of filtered) {
    const card=document.createElement("article"); card.className="media-card"; card.tabIndex=0;
    const poster=document.createElement("div"); poster.className="poster-placeholder"; poster.textContent="▶"; card.appendChild(poster);
    const info=document.createElement("div"); info.className="media-info";
    const h=document.createElement("h3"); h.textContent=item.title||"Sem título";
    const p=document.createElement("p"); p.textContent=(item.category||"Filmes").toUpperCase();
    info.append(h,p); card.appendChild(info);
    card.addEventListener("click",()=>playItem(index));
    card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();playItem(index);}});
    grid.appendChild(card);
  }
}
async function loadCatalog() {
  try {
    const response=await fetch(CATALOG_URL+"?v="+Date.now(),{cache:"no-store"});
    if(!response.ok) throw new Error("HTTP "+response.status);
    const payload=await response.json();
    const raw=Array.isArray(payload)?payload:(Array.isArray(payload.items)?payload.items:[]);
    catalog=raw.map((item,index)=>({...item,title:item.title||("Vídeo "+(index+1)),category:item.category||"filmes",url:item.url||item.embed_url||""})).filter(item=>safeUrl(item.url));
    statusEl.textContent="Catálogo atualizado • "+catalog.length+" vídeos";
    render();
  } catch(error) {
    statusEl.textContent="Falha ao carregar catálogo";
    grid.innerHTML='<div class="empty-library">Não foi possível carregar ../data/catalog.json. Erro: '+String(error.message||error)+'</div>';
    console.error("OIO Media catalog:",error);
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
