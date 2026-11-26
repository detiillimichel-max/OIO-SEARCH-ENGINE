const CATALOG_URL = "../data/catalog.json";
const DRIVE_GATEWAY_URL = "https://oio-drive-gateway.vercel.app/api/catalog";
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
async function fetchGatewayCatalog() {
  const response = await fetch(DRIVE_GATEWAY_URL, { cache: "no-store" });
  let payload = null;
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) {
    const detail = payload && payload.error ? " — " + payload.error : "";
    throw new Error("Gateway: HTTP " + response.status + detail);
  }
  if (!payload || payload.ok !== true || !Array.isArray(payload.videos)) throw new Error((payload && payload.error) || "Resposta do Gateway sem catálogo válido.");
  return { payload, cache: response.headers.get("X-Catalog-Cache") || "" };
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
    const card=document.createElement("article"); card.className="media-card"; card.tabIndex=0; card.setAttribute("role","button"); card.setAttribute("aria-label","Reproduzir "+(item.title||"conteúdo"));
    const poster=document.createElement("div"); poster.className="poster-placeholder";
    const fileId=driveFileId(item.url);
    if(fileId){
      const image=document.createElement("img");
      image.className="poster-image";
      image.alt="";
      image.loading="lazy";
      image.src="https://drive.google.com/thumbnail?id="+encodeURIComponent(fileId)+"&sz=w640";
      image.addEventListener("error",()=>{image.remove();poster.classList.add("poster-fallback");},{once:true});
      poster.appendChild(image);
    } else poster.classList.add("poster-fallback");
    const shade=document.createElement("span"); shade.className="poster-shade";
    const playMark=document.createElement("span"); playMark.className="poster-play"; playMark.textContent="▶";
    const tag=document.createElement("span"); tag.className="poster-tag"; tag.textContent=(item.category||"FILMES").toUpperCase();
    poster.append(shade,playMark,tag); card.appendChild(poster);
    const info=document.createElement("div"); info.className="media-info";
    const h=document.createElement("h3"); h.textContent=item.title||"Sem título";
    const p=document.createElement("p"); p.textContent="▶  Assistir agora";
    info.append(h,p); card.appendChild(info);
    card.addEventListener("click",()=>playItem(index));
    card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();playItem(index);}});
    grid.appendChild(card);
  }
}
async function loadCatalog() {
  statusEl.textContent = "Carregando catálogo local e Gateway…";
  try {
    // As duas fontes são lidas separadamente. O catálogo local nunca é substituído.
    const [localResult, gatewayResult, driveBuscasResult] = await Promise.allSettled([
      fetch(CATALOG_URL + "?v=" + Date.now(), { cache: "no-store" }).then(async response => {
        if (!response.ok) throw new Error("Catálogo local: HTTP " + response.status);
        return response.json();
      }),
      fetchGatewayCatalog(),
      window.OIODriveBuscas.load()
    ]);

    let localItems = [];
    let gatewayItems = [];
    let driveBuscasItems = [];
    let driveBuscasMeta = {};
    let localError = null;
    let gatewayError = null;
    let driveBuscasError = null;
    let gatewayCache = "";

    if (localResult.status === "fulfilled") {
      const payload = localResult.value;
      localItems = Array.isArray(payload) ? payload : (Array.isArray(payload.items) ? payload.items : []);
    } else {
      localError = localResult.reason;
      console.warn("OIO Media: catálogo local indisponível.", localError);
    }

    if (gatewayResult.status === "fulfilled") {
      const payload = gatewayResult.value.payload;
      gatewayCache = gatewayResult.value.cache;
      if (payload && payload.ok === true && Array.isArray(payload.videos)) {
        // O Gateway só inclui itens cujo acesso anônimo foi confirmado.
        gatewayItems = payload.videos.map(video => ({
          id: video.id,
          title: video.title || video.name || "Vídeo sem título",
          url: video.url || video.webViewLink || video.previewUrl || "",
          poster: video.thumbnailUrl || "",
          category: "videos",
          description: "Arquivo listado no Google Drive pelo OIO-DRIVE-GATEWAY. Acesso público e reprodução ainda não verificados.",
          source: "OIO-DRIVE-GATEWAY",
          access: video.access || "ACCESS_UNKNOWN",
          playback_type: "drive_preview"
        }));
      } else {
        gatewayError = new Error("Resposta do Gateway sem catálogo válido.");
      }
    } else {
      gatewayError = gatewayResult.reason;
      console.warn("OIO Media: Gateway indisponível; mantendo catálogo local.", gatewayError);
    }

    if (driveBuscasResult.status === "fulfilled" && driveBuscasResult.value && Array.isArray(driveBuscasResult.value.items)) {
      driveBuscasItems = driveBuscasResult.value.items;
      driveBuscasMeta = driveBuscasResult.value.meta || {};
    } else {
      driveBuscasError = driveBuscasResult.status === "rejected"
        ? driveBuscasResult.reason
        : new Error("Adaptador Drive-buscas sem catálogo válido.");
      console.warn("OIO Media: importação Drive-buscas indisponível; mantendo as fontes existentes.", driveBuscasError);
    }

    if (localError && gatewayError) {
      throw new Error("Não foi possível carregar nenhuma fonte. " +
        String(localError.message || localError) + " / " +
        String(gatewayError.message || gatewayError));
    }

    // Mantém primeiro os itens antigos e acrescenta os novos sem duplicar IDs do Drive.
    const merged = [];
    const seen = new Set();
    for (const item of [...localItems, ...gatewayItems, ...driveBuscasItems]) {
      const url = item.url || item.previewUrl || item.embed_url || "";
      const key = String(item.id || driveFileId(url) || url).trim();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      merged.push({
        ...item,
        title: item.title || item.name || ("Vídeo " + (merged.length + 1)),
        category: item.category || "filmes",
        url
      });
    }

    catalog = merged.filter(item => safeUrl(item.url));
    const gatewayCount = gatewayItems.filter(item => safeUrl(item.url)).length;
    const localCount = localItems.filter(item => safeUrl(item.url)).length;
    const sourceLabel = gatewayError
      ? "Catálogo local • Gateway indisponível"
      : "Biblioteca integrada";
    const refreshLabel = gatewayCache === "REFRESHED" ? " • Drive atualizado agora"
      : gatewayCache === "COOLDOWN" ? " • atualização recente; cache preservado"
      : gatewayCache === "STALE" ? " • última cópia válida preservada"
      : gatewayCache === "HIT" ? " • cache do Gateway" : "";
    const driveBuscasCount = driveBuscasItems.filter(item => safeUrl(item.url)).length;
    const driveBuscasRawCount = Number(driveBuscasMeta.raw_records || driveBuscasCount);
    const driveBuscasDuplicateCount = Number(driveBuscasMeta.duplicate_records || 0);
    const importLabel = driveBuscasError
      ? " • Drive-buscas indisponível"
      : " • Drive-buscas: " + driveBuscasCount + " registros únicos de " + driveBuscasRawCount +
        " referências (" + driveBuscasDuplicateCount + " duplicadas)";
    statusEl.textContent = sourceLabel + " • " + catalog.length +
      " itens (" + localCount + " catálogo original + " + gatewayCount + " Gateway antes de deduplicar)" + importLabel + refreshLabel;
    render();
  } catch (error) {
    statusEl.textContent = "Falha ao carregar catálogo";
    grid.replaceChildren();
    const message = document.createElement("div");
    message.className = "empty-library";
    message.textContent = "Não foi possível carregar o catálogo. " + String(error.message || error);
    grid.appendChild(message);
    console.error("OIO Media catalog:", error);
  } finally {
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


// Abas de status: o conteúdo existente permanece isolado e inalterado.
document.querySelectorAll("[data-workspace]").forEach(button => {
  button.addEventListener("click", () => {
    const target = button.dataset.workspace;
    document.querySelectorAll("[data-workspace]").forEach(tab => tab.classList.toggle("active", tab === button));
    document.querySelectorAll(".workspace-panel").forEach(panel => {
      const active = panel.id === (target === "existing" ? "workspace-existing" : "workspace-defined");
      panel.hidden = !active;
      panel.classList.toggle("active", active);
    });
  });
});


// Camada separada de descobertas: não altera nem substitui data/catalog.json.
const DISCOVERY_URL = "../data/discovery-candidates.json";
const DISCOVERY_LIBRARY_URL = "../data/discovery-library.json";
const discoveryGrid = document.getElementById("discovery-grid");
const discoveryCount = document.getElementById("discovery-count");
const discoverySearch = document.getElementById("discovery-search");
let discoveries = [];
let discoveryStatus = "all";
let discoveryTerm = "";

const discoveryLabels = {
  page_reachable_unverified: "Página respondeu · não confirmada",
  login_required: "Exige login",
  restricted: "Restrito",
  unknown: "Sem verificação"
};
function renderDiscoveries() {
  if (!discoveryGrid) return;
  const filtered = discoveries.filter(item => {
    const statusOk = discoveryStatus === "all" || item.category === discoveryStatus;
    const text = [item.title, item.name, item.url, item.kind, item.category, item.folder_title].join(" ").toLocaleLowerCase("pt-BR");
    return statusOk && text.includes(discoveryTerm);
  });
  discoveryCount.textContent = discoveries.length + " candidatos encontrados · " + filtered.length + " exibidos";
  discoveryGrid.replaceChildren();
  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty-library";
    empty.textContent = discoveries.length ? "Nenhuma descoberta corresponde ao filtro." : "Nenhum candidato disponível.";
    discoveryGrid.appendChild(empty);
    return;
  }
  for (const item of filtered) {
    const card = document.createElement("article");
    card.className = "discovery-card";
    const heading = document.createElement("div");
    heading.className = "discovery-card-heading";
    const title = document.createElement("h3");
    title.textContent = item.title || item.name || (item.kind === "folder" ? "Pasta pública candidata" : "Arquivo candidato");
    const status = document.createElement("span");
    status.className = "discovery-status status-" + item.verification_status;
    status.textContent = discoveryLabels[item.verification_status] || discoveryLabels.unknown;
    heading.append(title, status);
    if (item.thumbnail) {
      const poster = document.createElement("img");
      poster.className = "discovery-thumbnail";
      poster.loading = "lazy";
      poster.alt = "";
      poster.src = item.thumbnail;
      poster.addEventListener("error", () => poster.remove(), { once: true });
      card.appendChild(poster);
    }
    const details = document.createElement("p");
    details.textContent = [item.folder_path || item.folder_title, item.kind || "item", item.source || "coleção pública"].filter(Boolean).join(" · ");
    const evidence = document.createElement("p");
    evidence.className = "discovery-evidence";
    evidence.textContent = item.evidence || "Ainda não há evidência de acesso anônimo.";
    const link = document.createElement("a");
    link.className = "discovery-open";
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = item.kind === "folder" ? "Abrir pasta no Drive ↗" : "Abrir item no Drive ↗";
    card.append(heading, details, evidence, link);
    discoveryGrid.appendChild(card);
  }
}
async function loadDiscoveries() {
  if (!discoveryGrid) return;
  try {
    const response = await fetch(DISCOVERY_LIBRARY_URL + "?v=" + Date.now(), {cache:"no-store"});
    if (!response.ok) throw new Error("Catálogo multimídia: HTTP " + response.status);
    const payload = await response.json();
    discoveries = (payload.items || []).flatMap(folder =>
      (folder.files || []).map(file => ({
        ...file,
        title: file.name || "Arquivo de mídia",
        folder_title: folder.title || "Pasta do Google Drive",
        url: file.url,
        category: file.category,
        kind: "file",
        verification_status: "listed",
        evidence: "Arquivo identificado na listagem pública da pasta."
      }))
    ).filter(item => safeUrl(item.url) && ["videos","filmes_series","desenhos_animacoes","musicas"].includes(item.category));
    renderDiscoveries();
    if (!discoveries.length) {
      discoveryCount.textContent = "Nenhum arquivo de mídia listado ainda";
    }
  } catch (error) {
    discoveryCount.textContent = "Catálogo multimídia ainda não gerado";
    discoveryGrid.replaceChildren();
    const message = document.createElement("div");
    message.className = "empty-library";
    message.textContent = "Execute o workflow OIO Media Folder Classification no GitHub Actions. " + (error.message || error);
    discoveryGrid.appendChild(message);
    console.error("OIO discoveries:", error);
  }
}
if (discoverySearch) discoverySearch.addEventListener("input", () => {
  discoveryTerm = discoverySearch.value.trim().toLocaleLowerCase("pt-BR");
  renderDiscoveries();
});
document.querySelectorAll("[data-discovery-status]").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll("[data-discovery-status]").forEach(tab => tab.classList.toggle("active", tab === button));
  discoveryStatus = button.dataset.discoveryStatus;
  renderDiscoveries();
}));
loadDiscoveries();
