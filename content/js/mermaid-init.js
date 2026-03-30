// Initialize mermaid.js for rendering diagrams in blog articles
// Usage: add JS: mermaid-init.js in article metadata
// Then use <pre class="mermaid">...</pre> blocks in content
//
// Style: Hand-drawn sketch — always rendered in LIGHT mode for readability.
// Works in Chrome & Brave, light & dark OS themes.

document.addEventListener("DOMContentLoaded", function () {
  var script = document.createElement("script");
  script.src =
    "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js";
  script.onload = function () {
    mermaid.initialize({
      startOnLoad: true,
      look: "handDrawn",
      theme: "default",
      securityLevel: "strict",
      fontSize: 14,
      flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        curve: "basis",
        nodeSpacing: 30,
        rankSpacing: 40,
        padding: 15,
      },
      sequence: {
        useMaxWidth: false,
        mirrorActors: true,
        actorFontSize: 14,
        messageFontSize: 13,
        noteFontSize: 12,
        width: 200,
        height: 50,
      },
      gantt: {
        useMaxWidth: false,
        fontSize: 13,
        sectionFontSize: 14,
        numberSectionStyles: 4,
        barHeight: 24,
        barGap: 6,
      },
      state: { useMaxWidth: false },
      themeVariables: {
        background: "#ffffff",
        primaryColor: "#ffffff",
        primaryTextColor: "#2d2d2d",
        primaryBorderColor: "#c2185b",
        secondaryColor: "#fff59d",
        secondaryTextColor: "#2d2d2d",
        tertiaryColor: "#f3e5f5",
        tertiaryTextColor: "#2d2d2d",
        lineColor: "#555555",
        textColor: "#2d2d2d",
        mainBkg: "#ffffff",
        nodeBorder: "#c2185b",
        clusterBkg: "#fafafa",
        clusterBorder: "#cccccc",
        titleColor: "#2d2d2d",
        edgeLabelBackground: "#ffffff",
        nodeTextColor: "#2d2d2d",
        /* Sequence diagram */
        actorBkg: "#ffffff",
        actorBorder: "#c2185b",
        actorTextColor: "#2d2d2d",
        actorLineColor: "#bbbbbb",
        noteBkgColor: "#fff59d",
        noteBorderColor: "#f9a825",
        noteTextColor: "#2d2d2d",
        signalColor: "#555555",
        signalTextColor: "#2d2d2d",
        activationBkgColor: "#e3f2fd",
        activationBorderColor: "#42a5f5",
        sequenceNumberColor: "#ffffff",
        labelBoxBkgColor: "#ffffff",
        labelBoxBorderColor: "#cccccc",
        labelTextColor: "#2d2d2d",
        loopTextColor: "#2d2d2d",
        /* Gantt chart */
        sectionBkgColor: "#f5f5f5",
        altSectionBkgColor: "#fafafa",
        gridColor: "#e0e0e0",
        taskBkgColor: "#e3f2fd",
        taskBorderColor: "#42a5f5",
        taskTextColor: "#2d2d2d",
        taskTextDarkColor: "#2d2d2d",
        taskTextOutsideColor: "#2d2d2d",
        doneTaskBkgColor: "#c8e6c9",
        doneTaskBorderColor: "#66bb6a",
        activeTaskBkgColor: "#fff59d",
        activeTaskBorderColor: "#f9a825",
        critBkgColor: "#fce4ec",
        critBorderColor: "#c2185b",
        todayLineColor: "#c2185b",
        /* State diagram */
        labelColor: "#2d2d2d",
        altBackground: "#fafafa",
      },
    });

    // Center scroll position of each mermaid container after render
    // and move all gantt task labels to the right of their bars
    mermaid.run().then(function () {
      // Gantt: force all task labels to appear right of bars
      document.querySelectorAll("pre.mermaid svg").forEach(function (svg) {
        var rects = svg.querySelectorAll("rect.task");
        var texts = svg.querySelectorAll(
          "text.taskText, text.taskTextOutsideRight, text.taskTextOutsideLeft"
        );
        if (rects.length === 0 || rects.length !== texts.length) return;
        for (var i = 0; i < texts.length; i++) {
          var r = rects[i];
          var t = texts[i];
          var rx = parseFloat(r.getAttribute("x"));
          var rw = parseFloat(r.getAttribute("width"));
          t.setAttribute("x", rx + rw + 5);
          t.style.textAnchor = "start";
          t.setAttribute("class", "taskTextOutsideRight");
        }
      });

      document.querySelectorAll("pre.mermaid").forEach(function (container) {
        var overflow = container.scrollWidth - container.clientWidth;
        if (overflow > 0) {
          container.scrollLeft = overflow / 2;
        }
      });
    });
  };
  document.head.appendChild(script);
});
