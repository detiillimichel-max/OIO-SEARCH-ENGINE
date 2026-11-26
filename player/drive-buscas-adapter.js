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

  function normalizeLabel(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR").replace(/\s+/g, " ").trim();
  }

  function isSeasonLine(line) {
    const value = normalizeLabel(line);
    return /^(?:(?:primeira|segunda|terceira|quarta|quinta|sexta|setima|oitava|nona|decima|\d{1,2}[ªº°]?)\s*(?:temporada|temp\.?)|(?:temporada|season)\s*(?:primeira|segunda|terceira|quarta|quinta|sexta|setima|oitava|nona|decima|\d{1,2}))$/i.test(value);
  }

  function isEpisodeLine(line) {
    return /^epis[oó]dio\s*\d+(?:\s+final)?$/i.test(String(line || "").trim());
  }

  function inferRecord(lines, category, url, lot, lineNumber, previousSeriesTitle, previousSeason) {
    const useful = lines
      .map(cleanContextLine)
      .filter(Boolean)
      .filter(line => !/^observa[cç][aã]o\b/i.test(line))
      .filter(line => !/^em ingl[eê]s$/i.test(line));

    const episode = useful.slice().reverse().find(isEpisodeLine) || "";
    const season = useful.slice().reverse().find(isSeasonLine) || previousSeason || "";
    const titleLines = useful.filter(line => !isSeasonLine(line) && !isEpisodeLine(line));
    let title = "";
    let finalCategory = category;
    let seriesTitle = previousSeriesTitle || "";
    let seriesSeason = previousSeason || "";

    if (episode) {
      const currentTitle = titleLines.length ? titleLines[titleLines.length - 1] : "";
      if (currentTitle) seriesTitle = currentTitle;
      if (season) seriesSeason = season;
      if (seriesTitle) {
        title = seriesTitle + (seriesSeason ? " — " + seriesSeason : "") + " — " + episode;
      } else {
        title = episode;
      }
      finalCategory = "series";
    } else if (useful.length && isSeasonLine(useful[useful.length - 1])) {
      const currentTitle = titleLines.length ? titleLines[titleLines.length - 1] : "";
      if (currentTitle) seriesTitle = currentTitle;
      seriesSeason = useful[useful.length - 1];
      title = (seriesTitle || "Série") + " — " + seriesSeason;
      finalCategory = "series";
    } else {
      title = useful.length ? useful[useful.length - 1] : (previousSeriesTitle || "Conteúdo sem título");
      if (finalCategory === "series") {
        seriesTitle = title;
        seriesSeason = season || "";
      } else {
        seriesTitle = "";
        seriesSeason = "";
      }
    }

    const isPhotos = /(?:photos\.google\.com|photos\.app\.goo\.gl)/i.test(url);
    const isFolder = /drive\.google\.com\/(?:drive\/(?:mobile\/)?folders\/|folders\/)/i.test(url);
    const recordType = isPhotos ? "google_photos_share" : (isFolder ? "drive_folder" : "drive_file");
    const id = extractSourceId(url);

    return {
      item: {
        id: id,
        title: title,
        url: url,
        category: finalCategory,
        source: "DRIVE_BUSCAS",
        source_id: id,
        source_key: "DRIVE_BUSCAS:" + recordType + ":" + id + ":" + normalizeLabel(title),
        record_type: recordType,
        playback_type: recordType === "drive_file" ? "drive_preview" : "external",
        access: "UNVERIFIED",
        origin_lot: lot,
        origin_line: lineNumber,
        description: "Registro importado de " + lot + ". Acesso, autorização e reprodução ainda não verificados."
      },
      seriesTitle: seriesTitle,
      season: seriesSeason
    };
  }

  function parseLot(markdown, lot) {
    const lines = markdown.split(/\r?\n/);
    const items = [];
    let category = "filmes";
    let context = [];
    let currentSeriesTitle = "";
    let currentSeason = "";

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index].trim();
      if (!line) continue;

      if (/^(?:filmes?(?:\s+drive)?|s[eé]ries?)$/i.test(line)) {
        const nextCategory = classifyHeading(line, category);
        if (nextCategory !== category) {
          currentSeriesTitle = "";
          currentSeason = "";
        } else if (nextCategory === "series") {
          const priorTitles = context
            .map(cleanContextLine)
            .filter(Boolean)
            .filter(value => !isSeasonLine(value) && !isEpisodeLine(value));
          if (priorTitles.length) currentSeriesTitle = priorTitles[priorTitles.length - 1];
        }
        category = nextCategory;
        context = [];
        continue;
      }

      const nextCategory = classifyHeading(line, category);
      if (/^(?:filme|s[eé]rie)\s+/i.test(line)) {
        category = nextCategory;
        context = [line];
        currentSeriesTitle = "";
        currentSeason = "";
        continue;
      }
      if (nextCategory !== category) {
        category = nextCategory;
        context = [];
        currentSeriesTitle = "";
        currentSeason = "";
      }

      if (/^https?:\/\//i.test(line)) {
        const result = inferRecord(context, category, line, lot, index + 1, currentSeriesTitle, currentSeason);
        if (result.item.id) {
          items.push(result.item);
          currentSeriesTitle = result.seriesTitle;
          currentSeason = result.season;
        }
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
      const seen = new Map();
      const failedLots = [];
      let rawCount = 0;
      function titleQuality(value) {
        const title = String(value || "").trim();
        if (!title || /^(?:conte[uú]do sem t[ií]tulo|v[ií]deo sem t[ií]tulo|sem t[ií]tulo|arquivo)$/i.test(title)) return 0;
        return Math.min(1000, normalizeLabel(title).length);
      }
      for (const result of results) {
        if (result.status !== "fulfilled") {
          failedLots.push(String(result.reason && result.reason.message || result.reason));
          continue;
        }
        rawCount += result.value.items.length;
        for (const item of result.value.items) {
          const collection = item.record_type === "drive_folder" || item.record_type === "google_photos_share";
          const key = collection
            ? item.record_type + ":" + item.id + ":" + normalizeLabel(item.title)
            : "file:" + (item.id || item.url);
          if (seen.has(key)) {
            const existingIndex = seen.get(key);
            if (titleQuality(item.title) > titleQuality(items[existingIndex].title)) {
              items[existingIndex] = item;
            }
            continue;
          }
          seen.set(key, items.length);
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