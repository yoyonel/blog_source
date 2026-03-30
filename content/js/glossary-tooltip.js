// Glossary tooltip — replaces native title="" with styled popups
// for links matching a[href^="#glossary-"][title]
//
// Loaded after DOM content. Creates a single tooltip element and
// wires mouseenter/mouseleave/focus/blur on glossary anchors.

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

  // --- Show ---
  function showTooltip(anchor) {
    clearTimeout(hideTimer);
    var titleText = anchor.getAttribute("data-glossary-title");
    if (!titleText) return;

    var parsed = parseTitleText(titleText);
    if (parsed.term) {
      termEl.textContent = parsed.term;
      termEl.style.display = "";
    } else {
      termEl.style.display = "none";
    }
    descEl.textContent = parsed.desc;

    // Make visible to measure, then position
    tip.style.opacity = "0";
    tip.style.display = "block";
    tip.classList.remove("visible");

    positionTooltip(anchor);

    // Trigger transition
    requestAnimationFrame(() => {
      tip.classList.add("visible");
      tip.style.opacity = "";
    });
  }

  // --- Hide ---
  function hideTooltip() {
    hideTimer = setTimeout(() => {
      tip.classList.remove("visible");
      // After transition, move off-screen
      setTimeout(() => {
        if (!tip.classList.contains("visible")) {
          tip.style.display = "none";
        }
      }, 250);
    }, 80);
  }

  // --- Wire up all glossary anchors ---
  function initAnchors() {
    const anchors = document.querySelectorAll('a[href^="#glossary-"][title]');
    for (let i = 0; i < anchors.length; i++) {
      const a = anchors[i];
      // Move title to data attribute to suppress native tooltip
      a.setAttribute("data-glossary-title", a.getAttribute("title"));
      a.removeAttribute("title");

      a.addEventListener("mouseenter", function () {
        showTooltip(this);
      });
      a.addEventListener("mouseleave", hideTooltip);
      a.addEventListener("focus", function () {
        showTooltip(this);
      });
      a.addEventListener("blur", hideTooltip);
    }
  }

  // --- Init on DOM ready ---
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAnchors);
  } else {
    initAnchors();
  }
})();
