// Initialize mermaid.js for rendering diagrams in blog articles
// Usage: add JS: mermaid-init.js in article metadata
// Then use <pre class="mermaid">...</pre> blocks in content

document.addEventListener("DOMContentLoaded", function () {
  // Detect dark mode from OS preference or body class
  var isDark =
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  // Flex theme also sets a data attribute or class
  var body = document.body;
  if (
    body.classList.contains("dark") ||
    document.documentElement.getAttribute("data-theme") === "dark"
  ) {
    isDark = true;
  }

  var script = document.createElement("script");
  script.src =
    "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js";
  script.onload = function () {
    mermaid.initialize({
      startOnLoad: true,
      theme: isDark ? "dark" : "default",
      securityLevel: "strict",
      fontSize: 14,
      flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        curve: "basis",
        nodeSpacing: 30,
        rankSpacing: 40,
        padding: 12,
      },
      sequence: {
        useMaxWidth: false,
        mirrorActors: true,
        actorFontSize: 13,
        messageFontSize: 13,
        noteFontSize: 12,
        width: 180,
        height: 50,
      },
      gantt: { useMaxWidth: false, fontSize: 12 },
      state: { useMaxWidth: false },
      themeVariables: isDark
        ? {
            darkMode: true,
            background: "#1a1a2e",
            primaryColor: "#2d5986",
            primaryTextColor: "#e0e0e0",
            primaryBorderColor: "#4a90d9",
            secondaryColor: "#3d2d5c",
            secondaryTextColor: "#e0e0e0",
            tertiaryColor: "#2d4a3d",
            tertiaryTextColor: "#e0e0e0",
            lineColor: "#7eb8da",
            textColor: "#e0e0e0",
            mainBkg: "#2d5986",
            nodeBorder: "#4a90d9",
            clusterBkg: "#1e3a5f",
            clusterBorder: "#4a90d9",
            titleColor: "#ffffff",
            edgeLabelBackground: "#1a1a2e",
            nodeTextColor: "#e0e0e0",
          }
        : {},
    });
  };
  document.head.appendChild(script);
});
