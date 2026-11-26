(function () {
  "use strict";

  const LOTS = [
    "https://raw.githubusercontent.com/detiillimichel-max/Drive-buscas-/main/lotes/lote-001.md",
    "https://raw.githubusercontent.com/detiillimichel-max/Drive-buscas-/main/lotes/lote-002.md",
    "https://raw.githubusercontent.com/detiillimichel-max/Drive-buscas-/main/lotes/lote-003.md"
  ];

  function extractSourceId(url) {
    let match = url.match(/drive\.google\.com\/(?:file\/d\/|drive\/mobile\/folders\/|drive\/u\/\d+\/folders\/|folders\/)([A-Za-z0-9_-]+)/i);
    if (match) return match[1];
    match = url.match(/photos\.google\.com\/(?:share|photo)\/([A-Za-z0-9_-]+)/i);
    if (match) return match[1];
    match = url.match(/photos\.app\.goo\.gl\/([A-Za-z0-9_-]+)/i);
    return match ? match[1] : null;
  }

  function classifyHeading(line, current) {
    const value = line.trim();
    if (/^filmes?(?:\s+drive)?$/i.test(value)) return "filmes";
    if (/^s[eé]ries?$/i.test(value)) return "series";
    if (/^s[eé]rie\s+/i.test(value)) return "series";
    if (/^filme\s+/i.test(value)) return "filmes";
    return current;
  }

  function cleanContextLine(line) {
    return line
      .replace(/^(?:filmes?|filme|s[eé]ries?|s[eé]rie)\s+/i, "")
      .trim();
  }

  function inferRecord(lines, category, url, lot, lineNumber) {
    const useful = lines
      .map(cleanContextLine)
      .filter(Boolean)
      .filter(line => !/^observa[cç][aã]o\b/i.test(line))
      .filter(line => !/^em ingl[eê]s$/i.test(line));

    let title = useful.length ? useful[useful.length - 1] : "Conteúdo sem título";
    if (/^epis[oó]dio\s*\d+/i.test(title) && useful.length > 1) {
      title = useful[useful.length - 2] + " — " + title;
    }

    let finalCategory = category;
    if (/temporada|epis[oó]dio/i.test(title)) finalCategory = "series";

    const isPhotos = /(?:photos\.google\.com|photos\.app\.goo\.gl)/i.test(url);
    const isFolder = /drive\.google\.com\/(?:drive\/(?:mobile\/)?folders\/|folders\/)/i.test(url);
    const recordType = isPhotos ? "google_photos_share" : (isFolder ? "drive_folder" : "drive_file");
    const id = extractSourceId(url);

    return {
      id: id,
      title: title,
      url: url,
      category: finalCategory,
      source: "DRIVE_BUSCAS",
      source_id: id,
      source_key: "DRIVE_BUSCAS:" + recordType + ":" + id,
      record_type: recordType,
      playback_type: recordType === "drive_file" ? "drive_preview" : "external",
      access: "UNVERIFIED",
      origin_lot: lot,
      origin_line: lineNumber,
      description: "Registro importado de " + lot + ". Acesso, autorização e reprodução ainda não verificados."
    };
  }

  function parseLot(markdown, lot) {
    const lines = markdown.split(/\r?\n/);
    const items = [];
    let category = "filmes";
    let context = [];

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index].trim();
      if (!line) continue;

      const nextCategory = classifyHeading(line, category);
      if (nextCategory !== category || /^(?:filmes?|s[eé]ries?)$/i.test(line)) {
        category = nextCategory;
        if (/^(?:filmes?|s[eé]ries?)$/i.test(line) || /^(?:filme|s[eé]rie)\s+/i.test(line)) {
          if (/^(?:filme|s[eé]rie)\s+/i.test(line)) context.push(line);
          else context = [];
          continue;
        }
      }

      if (/^https?:\/\//i.test(line)) {
        const item = inferRecord(context, category, line, lot, index + 1);
        if (item.id) items.push(item);
        context = [];
        continue;
      }

      context.push(line);
    }
    return items;
  }

  let cachedLoad = null;

  async function load() {
    if (cachedLoad) return cachedLoad;
    cachedLoad = (async function () {
      const results = await Promise.allSettled(LOTS.map(async function (url) {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status + " ao ler " + url);
        const lot = url.split("/").pop();
        return { lot: lot, items: parseLot(await response.text(), lot) };
      }));

      const items = [];
      const seen = new Set();
      const failedLots = [];
      let rawCount = 0;
      for (const result of results) {
        if (result.status !== "fulfilled") {
          failedLots.push(String(result.reason && result.reason.message || result.reason));
          continue;
        }
        rawCount += result.value.items.length;
        for (const item of result.value.items) {
          const key = item.id || item.url;
          if (seen.has(key)) continue;
          seen.add(key);
          items.push(item);
        }
      }

      if (!items.length && failedLots.length === LOTS.length) {
        throw new Error("Não foi possível ler nenhum lote do Drive-buscas: " + failedLots.join(" | "));
      }

      return {
        items: items,
        meta: {
          source: "Drive-buscas-",
          lots_read: LOTS.length - failedLots.length,
          lots_failed: failedLots.length,
          raw_records: rawCount,
          unique_records: items.length,
          duplicate_records: rawCount - items.length,
          failed_lots: failedLots
        }
      };
    })();
    return cachedLoad;
  }

  window.OIODriveBuscas = { load: load };
})();