# Optimisation des performances de chargement

> Date : 2026-03-31
> Branche : `perf/optimize-page-load`
> Page de test : `suckless-ogl-anatomie-frame.html`
> Preview : [bloggy-perf-test.surge.sh](https://bloggy-perf-test.surge.sh/suckless-ogl-anatomie-frame.html)

## Résultats — Core Web Vitals (Lighthouse, desktop, médiane de 3 runs)

| Métrique | Avant optimisation | Après optimisation | Seuil « bon » |
|----------|-------------------:|-------------------:|:--------------:|
| **Performance Score** | 39 | **80** | ≥ 90 |
| **First Contentful Paint (FCP)** | 4.04 s | **1.73 s** 🟢 | ≤ 1.8 s |
| **Largest Contentful Paint (LCP)** | 6.81 s | **2.21 s** 🟢 | ≤ 2.5 s |
| **Total Blocking Time (TBT)** | 0 ms | **15 ms** 🟢 | ≤ 200 ms |
| **Cumulative Layout Shift (CLS)** | 0.33 | **0.02** 🟢 | ≤ 0.1 |
| **Speed Index (SI)** | 5.78 s | **1.73 s** 🟢 | ≤ 3.4 s |

> Mesures réalisées via `just audit` (Lighthouse CLI, Chromium headless, desktop
> simulated throttling, médiane de 3 runs). Le temps de chargement initial de
> la page était > 10 s (Network tab, Brave DevTools) avant toute optimisation.

## Contexte

La page [suckless-ogl-anatomie-frame.html](https://yoyonel.github.io/suckless-ogl-anatomie-frame.html)
prenait **plus de 10 secondes** à charger. L'analyse du panneau Network de DevTools a
révélé 3 causes principales :

| Cause | Impact estimé |
|-------|---------------|
| **Disqus** chargé immédiatement (embed.js + WebSocket + trackers) | 5-8s |
| **Google Analytics UA** (obsolète depuis juillet 2024, timeouts) | 1-2s |
| **22 images PNG/JPG non optimisées** (16 Mo total, pas de lazy loading) | 2-4s |

## Modifications apportées

### 1. Disqus — chargement différé via IntersectionObserver

**Fichier** : `themes/Flex/templates/partial/disqus.html`

**Avant** : `embed.js` était chargé dès le parsing du HTML, ce qui déclenchait
immédiatement un WebSocket persistant, des stylesheets, et des trackers internes
(aifie, pixel.gif, lounge.bundle.js).

**Après** : Un `IntersectionObserver` avec `rootMargin: '200px'` ne charge Disqus
que lorsque l'utilisateur scroll à proximité de la section commentaires.

```javascript
// Chargement déclenché seulement quand #disqus_thread est visible
var observer = new IntersectionObserver(function(entries) {
    if (entries[0].isIntersecting) {
        loadDisqus();
        observer.disconnect();
    }
}, { rootMargin: '200px' });
observer.observe(document.getElementById('disqus_thread'));
```

**Fallback** : Pour les navigateurs sans IntersectionObserver, chargement différé
de 2s après l'événement `load`.

### 2. Google Analytics — supprimé

**Fichiers** : `publishconf.py`, `pelicanconf.py`

L'identifiant `UA-155727660-1` (Universal Analytics) est **hors service depuis
juillet 2024**. Le script `analytics.js` tentait de contacter des serveurs qui
répondaient lentement ou pas du tout, ajoutant de la latence inutile.

```python
# publishconf.py — commenté
# GOOGLE_ANALYTICS = "UA-155727660-1"
```

> **Pour réactiver des analytics** : utiliser GA4 (`G-XXXXXXXXXX`) via
> `GOOGLE_GLOBAL_SITE_TAG` dans `publishconf.py`, ou Plausible via `PLAUSIBLE_DOMAIN`.
> Les deux sont déjà supportés par le thème Flex.

### 3. Images — conversion PNG/JPG → WebP

**Fichiers** : `content/images/suckless-ogl/*.webp`, articles FR et EN

Conversion de 22 images via `cwebp -q 85` :

| Format | Taille totale | Réduction |
|--------|---------------|-----------|
| PNG/JPG (avant) | 16 Mo | — |
| WebP (après) | 2 Mo | **-87%** |

Les références ont été mises à jour dans les deux articles (FR + EN).

Les fichiers PNG/JPG originaux sont conservés dans le repo comme backup mais ne
sont plus référencés par aucun article.

### 4. Images — lazy loading + dimensions automatiques (anti-CLS)

**Fichier** : `plugins/lazy_images.py` (nouveau plugin)

Plugin Pelican qui post-traite le HTML généré pour :

1. **`loading="lazy"`** sur toutes les `<img>` qui n'ont pas déjà l'attribut
2. **`width` / `height`** auto-détectés depuis les fichiers images locaux

L'ajout des dimensions est essentiel pour le **CLS** : sans elles, le navigateur
ne réserve pas d'espace, puis décale tout le contenu quand l'image se charge.

```python
# Détection des dimensions sans dépendance externe
# Supporte : WebP (VP8/VP8L/VP8X), PNG, GIF, JPEG
w, h = _get_image_dimensions(img_path)
# Résultat dans le HTML :
# <img width="1024" height="768" loading="lazy" src="..." alt="...">
```

> Le plugin lit uniquement les headers binaires des fichiers (30 octets max)
> pour extraire les dimensions — aucune bibliothèque d'imagerie requise.

Activé dans `pelicanconf.py` :

```python
PLUGINS = ["css_js_injector", "lazy_images", "mermaid_prerender", "i18n_subsites"]
```

### 5. Mermaid — pré-rendu SVG au build (suppression du JS client)

**Fichier** : `plugins/mermaid_prerender.py` (nouveau plugin)

La page contenait 17 diagrammes mermaid rendus côté client via `mermaid.min.js`
(~800 Ko). Le chargement + exécution de ce script bloquait le rendu pendant ~5s.

**Solution** : Un plugin Pelican qui pré-rend les blocs `<pre class="mermaid">`
en SVG inline via `mmdc` (mermaid-cli) au moment du build.

**Optimisations du plugin** :

| Technique | Effet |
|-----------|-------|
| Cache disque SHA256 (`.mermaid-cache/`) | Build incrémental quasi-instantané |
| Rendu parallèle (ThreadPoolExecutor, 4 workers) | Cold build 138s → 69s |
| Cache mémoire in-process | Déduplique FR/EN si diagrammes identiques |
| IDs SVG uniques par diagramme | Évite les collisions CSS/JS |
| **svgo** post-processing | **-60%** taille SVG (2.6 Mo → 1.0 Mo) |
| Wrapper CSS flex (`.mermaid-center`) | Centrage sans JS → **CLS = 0** |

**Fichiers de configuration** :

- `mermaid.config.json` : variables de thème (`look: "handDrawn"`, couleurs, polices)
  extraites de `mermaid-init.js`
- `puppeteer.json` : chemin vers chromium pour mmdc

**Temps de build** :

| Scénario | Durée |
|----------|-------|
| Sans plugin (avant) | ~3s |
| Cold build (cache vide, mmdc + svgo) | ~105s |
| Warm build (cache plein) | ~2.5s |

**Impact page** : supprime ~800 Ko de JS + ~5s de rendu client → diagrammes
visibles instantanément au chargement de la page.

#### Centrage CSS des diagrammes larges (anti-CLS)

L'ancien `mermaid-init.js` centrait les diagrammes via `scrollLeft = overflow / 2`
en JavaScript — ce qui provoquait un **layout shift** visible (CLS = 0.33).

Le plugin injecte maintenant un wrapper `<span class="mermaid-center">` autour de
chaque SVG, centré en CSS pur :

```css
/* content/css/mermaid-dark.css */
pre.mermaid .mermaid-center {
  display: inline-flex;
  justify-content: center;
  min-width: 100%;
}
```

Le SVG est centré dès le premier paint, sans aucun recalcul JavaScript.

#### Optimisation SVG via svgo

Chaque SVG rendu par mmdc est optimisé automatiquement par
[svgo](https://github.com/nicolo-ribaudo/svgo) (installé en devDependency npm) :

```
Original : 2.6 Mo de SVG inline (17 diagrammes handDrawn)
Optimisé : 1.0 Mo (-60%)
HTML total : 2.76 Mo → 1.19 Mo
```

L'optimisation est effectuée **avant** la mise en cache, donc le cold build la
fait une seule fois par diagramme.

#### Script Gantt résiduel

Un petit script inline est injecté avant `</body>` pour repositionner les labels
des tâches Gantt à droite de leurs barres et centrer le scroll horizontal des
diagrammes larges (`scrollLeft = overflow / 2`). Ce script s'exécute sur
`window.load` (pas `DOMContentLoaded`) pour éviter le warning Firefox
« Layout was forced before the page was fully loaded ».

### 6. Analyse profiler Firefox — optimisations réseau et rendu

L'analyse du profiler Firefox (Call Tree + Network) a révélé deux goulots
d'étranglement résiduels :

| Problème | Impact profiler |
|----------|-----------------|
| **Paint des 17 SVGs hand-drawn** | 26% CPU (self) |
| **Reflow du HTML 1.2 Mo** | 13% CPU |
| **Google Fonts sans preconnect** | DNS+TCP+TLS round-trips supplémentaires |

**Fichier** : `plugins/html_optimizer.py` (nouveau plugin)

#### 6a. Preconnect Google Fonts

Injection automatique de `<link rel="preconnect">` en tout début de `<head>`,
avant le `<link>` du stylesheet Google Fonts :

```html
<head>
  <link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <!-- ... puis le stylesheet fonts.googleapis.com/css2 ... -->
```

Cela élimine les round-trips DNS + TCP + TLS pour `fonts.gstatic.com` qui
servait les fichiers `.woff2` (Source Sans Pro, Source Code Pro).

#### 6b. Lazy-load des SVGs mermaid hors viewport

Sur les 17 diagrammes SVG inline, seuls les 2 premiers sont visibles au
chargement initial (above the fold). Les 15 suivants sont wrappés dans des
`<template>` (non parsés/rendus par le navigateur) et révélés via
`IntersectionObserver` quand l'utilisateur s'en approche (rootMargin 400px).

```html
<!-- Eager (above the fold) -->
<pre class="mermaid"><span class="mermaid-center"><svg ...>...</svg></span></pre>

<!-- Lazy (below the fold) -->
<pre class="mermaid" data-lazy-svg>
  <template><span class="mermaid-center"><svg ...>...</svg></span></template>
</pre>
```

**Impact** : réduit de ~85% le travail initial de Paint (2 SVGs au lieu de 17).

#### 6c. Corrections console Firefox

| Warning | Fix |
|---------|-----|
| `Layout was forced before the page was fully loaded` | Script mermaid : `DOMContentLoaded` → `window.load` |
| `favicon.ico 404` | Favicon 32×32 généré depuis avatar.gif (`FAVICON` dans pelicanconf) |
| `Found a sectioned h1 with no specified font-size` | `content/css/custom.css` : `article/aside/section h1 { font-size: 2em }` |

> Les warnings `Glyph bbox was incorrect` sur Font Awesome et Architects Daughter
> sont des problèmes dans les polices upstream — non corrigeables côté blog.

## Résumé des fichiers modifiés

| Fichier | Type de modification |
|---------|---------------------|
| `pelicanconf.py` | Ajout plugins `lazy_images` + `mermaid_prerender` + `html_optimizer` |
| `publishconf.py` | Commenté `GOOGLE_ANALYTICS`, réactivé `DISQUS_SITENAME` |
| `themes/Flex/templates/partial/disqus.html` | IntersectionObserver lazy-load |
| `plugins/lazy_images.py` | **Nouveau** — lazy loading + dimensions auto |
| `plugins/mermaid_prerender.py` | **Nouveau** — pré-rendu SVG + svgo + cache |
| `plugins/html_optimizer.py` | **Nouveau** — preconnect + lazy SVGs |
| `mermaid.config.json` | **Nouveau** — config thème mermaid (handDrawn) |
| `puppeteer.json` | **Nouveau** — chemin chromium pour mmdc |
| `content/css/mermaid-dark.css` | Ajout `.mermaid-center` (flex centering) |
| `content/suckless-ogl-anatomie-frame.md` | Refs images → `.webp`, supprimé `mermaid-init.js` |
| `content/suckless-ogl-anatomie-frame-en.md` | Refs images → `.webp`, supprimé `mermaid-init.js` |
| `content/images/suckless-ogl/*.webp` | **Nouveau** — 22 images WebP |
| `content/images/favicon.ico` | **Nouveau** — favicon 32×32 depuis avatar.gif |
| `content/css/custom.css` | **Nouveau** — fix h1 sectioned (Firefox warning) |
| `scripts/lighthouse-audit.sh` | **Nouveau** — audit Lighthouse local + comparaison |
| `Justfile` | Ajout recette `audit` |
| `.gitignore` | Ajout `.mermaid-cache/`, `lighthouse-reports/` |
| `package.json` | Ajout devDeps `lighthouse`, `svgo` |

## Audit de performances local

Un script Lighthouse CLI permet de **mesurer les Core Web Vitals localement**
avant chaque push, sans dépendre d'outils en ligne.

### Usage

```bash
# Auditer la page par défaut (suckless-ogl-anatomie-frame.html)
just audit

# Auditer une page spécifique
just audit python-helloworld.html

# Équivalent direct
./scripts/lighthouse-audit.sh suckless-ogl-anatomie-frame.html
```

### Ce que fait le script

1. Build le site si `output/` n'existe pas
2. Lance un serveur HTTP local (Python `http.server`)
3. Exécute Lighthouse CLI avec Chromium headless (desktop, simulated throttling)
4. Génère un rapport JSON + HTML dans `lighthouse-reports/`
5. Affiche un résumé des 6 métriques clés avec indicateurs couleur
6. **Compare automatiquement** avec le baseline s'il existe
   (`lighthouse-reports/baseline-before-profiler-fixes.json`)

### Exemple de sortie

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Core Web Vitals — suckless-ogl-anatomie-frame.html
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🟠 Performance Score                 80.00  (good: ≥90)
  🟢 First Contentful Paint             1.74s  (good: ≤1.8s)
  🟢 Largest Contentful Paint           2.21s  (good: ≤2.5s)
  🟢 Total Blocking Time               41.00ms  (good: ≤200ms)
  🟢 Cumulative Layout Shift            0.02  (good: ≤0.1)
  🟢 Speed Index                        1.74s  (good: ≤3.4s)

📄 Full report: lighthouse-reports/suckless-ogl-anatomie-frame.report.html
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Prérequis

- `chromium` dans le PATH (utilisé en headless)
- `lighthouse` (npm devDependency, installé via `npm install`)
- `python3` (pour le serveur HTTP local)

### Rapports

Les rapports HTML détaillés sont générés dans `lighthouse-reports/` (gitignored).
Ouvrir le `.report.html` dans un navigateur pour l'analyse complète avec les
recommandations Lighthouse.

### Méthode de benchmark fiable

Pour des résultats stables, exécuter 3 runs et prendre la médiane :

```bash
# Lancer le serveur
python3 -m http.server 9223 -d output &

# 3 runs
for i in 1 2 3; do
  npx lighthouse "http://localhost:9223/suckless-ogl-anatomie-frame.html" \
    --chrome-flags="--headless --no-sandbox" \
    --chrome-path="$(which chromium)" \
    --output=json --output-path="lighthouse-reports/run-$i" \
    --only-categories=performance --preset=desktop --quiet
done

# Comparer les résultats dans les fichiers run-*.report.json
kill %1
```

## Vérification

Après `just build`, vérifier dans le HTML généré :

```bash
# Images avec lazy loading + dimensions
grep -c 'loading="lazy"' output/suckless-ogl-anatomie-frame.html
grep -o 'width="[0-9]*" height="[0-9]*"' output/suckless-ogl-anatomie-frame.html | head -5

# Refs WebP, 0 PNG/JPG
grep -c '\.webp' output/suckless-ogl-anatomie-frame.html
grep -c 'suckless-ogl.*\.png\|suckless-ogl.*\.jpg' output/suckless-ogl-anatomie-frame.html

# Disqus lazy-loaded
grep 'IntersectionObserver' output/suckless-ogl-anatomie-frame.html

# Pas de Google Analytics
grep -c 'google-analytics\|GoogleAnalyticsObject' output/suckless-ogl-anatomie-frame.html

# 17 SVG mermaid inline, 0 mermaid.min.js
grep -c '<svg' output/suckless-ogl-anatomie-frame.html
grep -c 'mermaid.min.js' output/suckless-ogl-anatomie-frame.html

# Taille HTML (devrait être ~1.2 Mo grâce à svgo)
wc -c output/suckless-ogl-anatomie-frame.html

# Centrage CSS (pas de scrollLeft JS)
grep -c 'mermaid-center' output/suckless-ogl-anatomie-frame.html
grep -c 'scrollLeft' output/suckless-ogl-anatomie-frame.html

# Audit Lighthouse complet
just audit
```

## Glossaire — Core Web Vitals

| Métrique | Quoi ? | Bon seuil |
|----------|--------|-----------|
| **LCP** (Largest Contentful Paint) | Temps avant que le plus grand élément visible soit rendu | ≤ 2.5 s |
| **CLS** (Cumulative Layout Shift) | Somme des décalages visuels non attendus pendant le chargement | ≤ 0.1 |
| **INP** (Interaction to Next Paint) | Délai entre un clic/tap et la réponse visuelle | ≤ 200 ms |
| **FCP** (First Contentful Paint) | Temps avant le premier pixel de contenu | ≤ 1.8 s |
| **TBT** (Total Blocking Time) | Temps cumulé où le thread principal est bloqué (> 50ms) | ≤ 200 ms |
| **SI** (Speed Index) | Vitesse à laquelle le contenu visible se remplit | ≤ 3.4 s |

## Améliorations futures possibles

- Atteindre un score Performance ≥ 90 (actuellement 80)
- Supprimer les fichiers PNG/JPG originaux du repo (économiser ~14 Mo dans git)
- Remplacer Disqus par [giscus](https://giscus.app/) (GitHub Discussions, sans tracker)
- Mettre en place un analytics léger (Plausible / Cloudflare Web Analytics)

## CI — Audits Lighthouse automatiques

Deux workflows GitHub Actions surveillent les performances :

### `performance.yml` — Audit sur chaque PR et push master

- **Déclencheur** : `pull_request` (opened/synchronize/reopened) + `push` sur master/main
- **Process** :
  1. Build le site en local (pelicanconf.py)
  2. Lance un serveur HTTP local
  3. Exécute 3 runs Lighthouse (desktop, simulated throttling)
  4. Calcule la **médiane** des 3 runs
  5. Poste un **commentaire PR** avec tableau de métriques
  6. Échoue si le score perf est **< 50**
- **Artefacts** : Rapports JSON + HTML conservés 30 jours

### `deploy.yml` — Audit post-déploiement sur le site live

- **Déclencheur** : après le job `build-deploy` (push sur master)
- **Process** :
  1. Attend 30s la propagation du déploiement GitHub Pages
  2. Exécute 3 runs Lighthouse contre `https://yoyonel.github.io/`
  3. Calcule la médiane et affiche dans le **Job Summary**
- **Artefacts** : Rapports JSON + HTML conservés 30 jours

### Seuils

| Métrique | Seuil bon | Seuil CI (échec) |
|----------|-----------|------------------|
| Performance Score | ≥ 90 | < 50 |
| FCP | ≤ 1.8 s | — |
| LCP | ≤ 2.5 s | — |
| TBT | ≤ 200 ms | — |
| CLS | ≤ 0.1 | — |
| SI | ≤ 3.4 s | — |

### Usage local

```bash
# Lancer un audit Lighthouse local
just audit
```
