# Refactoring Mermaid — Style Hand-Drawn & Light-Mode Forcé

> Date : 2026-03-30
> Fichiers modifiés : `content/js/mermaid-init.js`, `content/css/mermaid-dark.css`,
> `content/suckless-ogl-anatomie-frame.md`, `content/suckless-ogl-anatomie-frame-en.md`

## Objectif

Migrer les 17 diagrammes Mermaid de l'article "Anatomie d'une frame" vers un style
hand-drawn (sketch/rough.js), avec fond **toujours clair** quel que soit le thème
du navigateur (light/dark), fonctionnel sur **Chrome, Firefox et Brave**.

## Obstacles techniques rencontrés

### 1. Brave auto-dark mode inverse les SVG

**Problème** : Brave applique un filtre CSS `filter: invert()` sur les éléments en
dark mode OS, rendant les diagrammes illisibles (texte clair sur fond clair inversé,
hachures rough.js inversées).

**Solution** :
- `color-scheme: light only !important` (le mot-clé `only` est crucial pour Brave/Chromium)
- `filter: none !important` + `-webkit-filter: none !important` sur `pre.mermaid`, `svg`, et `svg *`
- `forced-color-adjust: none !important` en cascade sur tous les enfants
- Sélecteurs spécifiques `.dark pre.mermaid` et `[data-theme="dark"] pre.mermaid` pour le thème Flex

**Leçon** : `color-scheme: light` seul ne suffit pas. C'est `light only` qui interdit
explicitement au navigateur d'appliquer toute transformation dark.

### 2. `look: "handDrawn"` ne s'applique qu'aux flowcharts et state diagrams

**Problème** : La doc Mermaid (v11.13.0) indique :
> *"Currently, [look: handDrawn] is supported for flowcharts and state diagrams,
> with plans to extend support to all diagram types."*

Les `sequenceDiagram`, `gantt`, et `stateDiagram-v2` gardent un rendu classique
même avec `look: "handDrawn"`.

**Leçon** : Pas de workaround propre. On accepte que flowcharts/state aient le rough.js
et que les autres types gardent un rendu classique avec les bonnes couleurs.

### 3. Police externe ("Architects Daughter") casse le dimensionnement des noeuds

**Problème** : En ajoutant une Google Font manuscrite (`fontFamily: "Architects Daughter"`)
via JS + CSS, les textes étaient systématiquement tronqués dans les noeuds.

**Cause racine** : Mermaid calcule les dimensions des noeuds (mesure bbox du texte)
au moment de `mermaid.initialize()` / `mermaid.run()`. Si la font n'est pas encore
chargée, il mesure avec la font fallback (plus étroite), puis la font manuscrite
(plus large) arrive et déborde.

**Tentative 1** : `startOnLoad: false` + `document.fonts.ready.then(() => mermaid.run())`
→ Amélioration partielle mais toujours des troncatures sur certains noeuds.
La font manuscrite est intrinsèquement plus large que ce que Mermaid prévoit
dans son calcul de padding.

**Tentative 2** : Augmenter `padding` de 15→20 et `width` de 180→200
→ Insuffisant, certains textes longs restent tronqués.

**Solution finale** : Supprimer complètement la font externe. `look: "handDrawn"`
apporte **sa propre font intégrée** via rough.js et dimensionne correctement
les noeuds pour celle-ci.

**Leçon** : Ne JAMAIS surcharger la fontFamily quand `look: "handDrawn"` est actif.
Mermaid handDrawn gère sa font en interne.

### 4. Résidus CSS dark-mode hors du `@media` block

**Problème** : Des styles dark-mode orphelins (`.mermaid .note { fill: #3d3d1a }`,
`.mermaid .task { fill: #2d5986 }`, etc.) étaient placés **en dehors** du bloc
`@media (prefers-color-scheme: dark)`, forçant des couleurs sombres sur les
Note boxes (sequence), barres Gantt, et clusters State.

**Solution** : Supprimé les résidus ; remplacé par des sélecteurs `pre.mermaid .note`,
`pre.mermaid .task`, etc. avec des couleurs light explicites (notes jaunes `#fff59d`,
barres bleues clair `#e3f2fd`, texte sombre `#2d2d2d`).

**Leçon** : Utiliser `pre.mermaid` comme préfixe (pas `.mermaid` seul) pour éviter
les conflits de spécificité.

### 5. themeVariables insuffisantes pour sequence/gantt/state

**Problème** : Les `themeVariables` initiales ne couvraient que les flowcharts.
Les sequence diagrams (acteurs, notes, signaux), gantt (barres, sections, grille),
et state diagrams (labels, clusters) prenaient les couleurs par défaut du thème
→ non cohérent avec le reste.

**Solution** : Ajout de ~30 themeVariables spécifiques :
- Sequence : `actorBkg`, `actorBorder`, `noteBkgColor`, `noteBorderColor`,
  `signalColor`, `activationBkgColor`, `labelBoxBkgColor`, `loopTextColor`, …
- Gantt : `sectionBkgColor`, `taskBkgColor`, `taskBorderColor`, `doneTaskBkgColor`,
  `activeTaskBkgColor`, `critBkgColor`, `gridColor`, `todayLineColor`, …
- State : `labelColor`, `altBackground`

## Architecture des styles

### Palette de couleurs (classDef)

| Classe | Fill | Border | Rôle |
|--------|------|--------|------|
| `entryExit` | `#fce4ec` | `#c2185b` | Points d'entrée/sortie (rose) |
| `keyFunc` | `#fff59d` | `#f9a825` | Fonctions-clés, surbrillance (jaune fluo) |
| `subsystem` | `#ffffff` | `#aaaaaa` | Neutre, pas de remplissage |
| `loopNode` | `#e3f2fd` | `#42a5f5` | Boucle de rendu (bleu pâle) |
| `compute` | `#f3e5f5` | `#ab47bc` | Compute shaders (violet) |
| `postfx` | `#fce4ec` | `#c2185b` | Post-processing (rose) |
| `highlight` | `#fff59d` | `#f9a825` | Mise en évidence (jaune) |
| `fallback` | `#f5f5f5` | `#bdbdbd` | Alternatives/fallbacks (gris) |

### Syntaxe Mermaid

- Noeuds arrondis : `("text")` au lieu de `["text"]` (rectangles à bords durs)
- Diamonds (décision) : `{"text"}` (inchangé)
- Subgraph labels : `["label"]` (syntaxe Mermaid obligatoire, ne pas changer)

## Limitations connues

1. **handDrawn limité aux flowcharts/state** — les sequence/gantt gardent un rendu
   classique (pas de rough.js sketchy borders)
2. **Pas de font manuscrite sur sequence/gantt** — laisser Mermaid gérer sa font,
   ne pas surcharger
3. **Brave `brave://flags/#enable-force-dark`** — si un utilisateur active ce flag
   expérimental, le `color-scheme: light only` peut ne plus suffire. Pas de fix côté auteur.
