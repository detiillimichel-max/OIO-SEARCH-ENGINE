(function () {
  "use strict";
  const grid = document.getElementById("media-grid");
  const heroTitle = document.getElementById("hero-title");
  const heroBackdrop = document.getElementById("hero-backdrop");
  const heroPlay = document.getElementById("hero-play-btn");
  const heroDescription = document.getElementById("hero-description");
  let featuredCard = null;

  function syncHero() {
    if (!grid) return;
    const card = grid.querySelector(".media-card");
    if (!card) return;
    const title = card.querySelector("h3");
    const poster = card.querySelector(".poster-image");
    featuredCard = card;
    if (title && heroTitle) heroTitle.textContent = title.textContent || "Descubra sua próxima história.";
    if (heroDescription) heroDescription.textContent = "Uma seleção da sua biblioteca OIO MEDIA. Escolha um título e comece a assistir.";
    if (poster && heroBackdrop) {
      heroBackdrop.style.backgroundImage = 'linear-gradient(90deg,#080b19 0%,transparent 100%),url("' + poster.src.replace(/"/g,"%22") + '")';
    }
    if (heroPlay) heroPlay.querySelector("span").textContent = "Assistir agora";
  }

  if (heroPlay) heroPlay.addEventListener("click", function () {
    if (featuredCard) featuredCard.click();
    else document.getElementById("biblioteca")?.scrollIntoView({behavior:"smooth"});
  });

  document.querySelectorAll("[data-bottom-category]").forEach(function (button) {
    button.addEventListener("click", function () {
      const category = button.dataset.bottomCategory;
      const filter = document.querySelector('.filter[data-category="' + category + '"]');
      if (filter) filter.click();
      document.getElementById("biblioteca")?.scrollIntoView({behavior:"smooth"});
      document.querySelectorAll(".bottom-link").forEach(link => link.classList.toggle("active", link === button));
    });
  });

  document.querySelectorAll('.bottom-link[href="#biblioteca"],.bottom-link[href="#discovery-grid"]').forEach(function (link) {
    link.addEventListener("click", function () {
      document.querySelectorAll(".bottom-link").forEach(item => item.classList.toggle("active", item === link));
    });
  });

  if (grid) {
    new MutationObserver(syncHero).observe(grid, {childList:true,subtree:true});
    syncHero();
  }
})();