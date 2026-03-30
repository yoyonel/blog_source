// Glossary & chapter-preview tooltips
// - Glossary: replaces native title="" with styled popups for a[href^="#glossary-"]
// - Chapter preview: shows a text excerpt on hover for TOC links (a[href^="#chapitre-"], a[href^="#chapter-"])
//
// Creates a single shared tooltip element reused for both.

(() => {
  // --- Create tooltip element ---
  var tip = document.createElement("div");
  tip.className = "glossary-tooltip";
  tip.setAttribute("role", "tooltip");
  tip.innerHTML =
    '<span class="tooltip-arrow"></span>' +
    '<span class="tooltip-term"></span>' +
    '<span class="tooltip-desc"></span>';
  document.body.appendChild(tip);

  var termEl = tip.querySelector(".tooltip-term");
  var descEl = tip.querySelector(".tooltip-desc");
  var hideTimer = null;

  // --- Parse "Term — Description" from title ---
  function parseTitleText(raw) {
    var sep = raw.indexOf(" — ");
    if (sep === -1) sep = raw.indexOf(" - ");
    if (sep !== -1) {
      return { term: raw.substring(0, sep).trim(), desc: raw.substring(sep + 3).trim() };
    }
    return { term: "", desc: raw.trim() };
  }

  // --- Extract preview text from chapter target ---
  function extractChapterPreview(href) {
    var id = href.replace(/^#/, "");
    var heading = document.getElementById(id);
    if (!heading) return null;

    var texts = [];
    var charCount = 0;
    var maxChars = 220;
    var el = heading.nextElementSibling;

    while (el && charCount < maxChars) {
      // Stop at next h2 (= next chapter), but traverse into sub-sections (h3/h4)
      if (el.tagName === "H2") break;
      // Only grab paragraph text, skip code blocks / tables / diagrams
      if (el.tagName === "P") {
        const text = el.textContent.trim();
        if (text) {
          texts.push(text);
          charCount += text.length;
        }
      }
      el = el.nextElementSibling;
    }

    if (texts.length === 0) return null;
    var preview = texts.join(" ");
    if (preview.length > maxChars) {
      preview = `${preview.substring(0, maxChars).replace(/\s+\S*$/, "")}…`;
    }
    return preview;
  }

  // --- Position tooltip near the anchor ---
  function positionTooltip(anchor) {
    var rect = anchor.getBoundingClientRect();
    var tipW = tip.offsetWidth;
    var tipH = tip.offsetHeight;
    var margin = 10;

    // Horizontal: center on anchor, clamp to viewport
    var left = rect.left + rect.width / 2 - tipW / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - tipW - 8));

    // Vertical: prefer below, flip above if no room
    var top = rect.bottom + margin;
    var arrowBottom = false;
    if (top + tipH > window.innerHeight - 8) {
      top = rect.top - tipH - margin;
      arrowBottom = true;
    }

    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;

    if (arrowBottom) {
      tip.classList.add("arrow-bottom");
    } else {
      tip.classList.remove("arrow-bottom");
    }

    // Position arrow horizontally relative to anchor center
    var arrow = tip.querySelector(".tooltip-arrow");
    var anchorCenter = rect.left + rect.width / 2 - left;
    anchorCenter = Math.max(16, Math.min(anchorCenter, tipW - 16));
    arrow.style.left = `${anchorCenter}px`;
  }

  // --- Show glossary tooltip ---
  function showGlossaryTooltip(anchor) {
    clearTimeout(hideTimer);
    var titleText = anchor.getAttribute("data-glossary-title");
    if (!titleText) return;

    tip.classList.remove("chapter-preview");
    var parsed = parseTitleText(titleText);
    if (parsed.term) {
      termEl.textContent = parsed.term;
      termEl.style.display = "";
    } else {
      termEl.style.display = "none";
    }
    descEl.textContent = parsed.desc;

    showTip(anchor);
  }

  // --- Show chapter preview tooltip ---
  function showChapterTooltip(anchor) {
    clearTimeout(hideTimer);
    var href = anchor.getAttribute("href");
    var preview = anchor.getAttribute("data-chapter-preview");
    var title = anchor.getAttribute("data-chapter-title");
    if (!preview && href) {
      preview = extractChapterPreview(href);
      if (preview) {
        anchor.setAttribute("data-chapter-preview", preview);
      }
    }
    if (!preview) return;

    tip.classList.add("chapter-preview");
    if (title) {
      termEl.textContent = title;
      termEl.style.display = "";
    } else {
      termEl.style.display = "none";
    }
    descEl.textContent = preview;

    showTip(anchor);
  }

  // --- Generic show ---
  function showTip(anchor) {
    tip.style.opacity = "0";
    tip.style.display = "block";
    tip.classList.remove("visible");

    positionTooltip(anchor);

    requestAnimationFrame(() => {
      tip.classList.add("visible");
      tip.style.opacity = "";
    });
  }

  // --- Hide ---
  function hideTooltip() {
    hideTimer = setTimeout(() => {
      tip.classList.remove("visible");
      setTimeout(() => {
        if (!tip.classList.contains("visible")) {
          tip.style.display = "none";
        }
      }, 250);
    }, 80);
  }

  // --- Wire up all glossary anchors ---
  function initGlossaryAnchors() {
    const anchors = document.querySelectorAll('a[href^="#glossary-"][title]');
    for (let i = 0; i < anchors.length; i++) {
      const a = anchors[i];
      a.setAttribute("data-glossary-title", a.getAttribute("title"));
      a.removeAttribute("title");

      a.addEventListener("mouseenter", function () {
        showGlossaryTooltip(this);
      });
      a.addEventListener("mouseleave", hideTooltip);
      a.addEventListener("focus", function () {
        showGlossaryTooltip(this);
      });
      a.addEventListener("blur", hideTooltip);
    }
  }

  // --- Wire up chapter TOC links ---
  function initChapterAnchors() {
    // Match French (#chapitre-) and English (#chapter-) anchor links
    var anchors = document.querySelectorAll('a[href^="#chapitre-"], a[href^="#chapter-"]');
    for (let i = 0; i < anchors.length; i++) {
      const a = anchors[i];
      // Find the chapter title from the target heading
      const href = a.getAttribute("href");
      const id = href.replace(/^#/, "");
      const heading = document.getElementById(id);
      if (heading) {
        a.setAttribute("data-chapter-title", heading.textContent.trim());
      }

      a.addEventListener("mouseenter", function () {
        showChapterTooltip(this);
      });
      a.addEventListener("mouseleave", hideTooltip);
      a.addEventListener("focus", function () {
        showChapterTooltip(this);
      });
      a.addEventListener("blur", hideTooltip);
    }
  }

  // --- Init on DOM ready ---
  function init() {
    initGlossaryAnchors();
    initChapterAnchors();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
