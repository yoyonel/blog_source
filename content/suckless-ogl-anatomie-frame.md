---
title: Anatomie d'une frame — Le cycle de vie complet de suckless-ogl
slug: suckless-ogl-anatomie-frame
lang: fr
date: 2026-03-29
description: Plongée technique illustrée dans le moteur de rendu PBR suckless-ogl — de main() jusqu'aux photons à l'écran. On retrace chaque étape du pipeline : initialisation OpenGL, chargement HDR asynchrone, ray-tracing de sphères par billboard, IBL progressive et post-processing cinématique.
tags: OpenGL, C, PBR, IBL, Rendu 3D, GLSL, Ray-Tracing, Post-Processing, Développement
category: Développement
CSS: mermaid-dark.css, glossary-tooltip.css
JS: mermaid-init.js (top), glossary-tooltip.js
---

# Anatomie d'une frame : le cycle de vie complet de suckless-ogl

*De `main()` aux photons sur l'écran — une plongée complète dans un moteur [PBR](#glossary-pbr "Physically-Based Rendering — modèle d'éclairage qui simule la physique réelle de la lumière") OpenGL moderne écrit en C.*

![Le rendu final de suckless-ogl — 100 sphères PBR éclairées par IBL]({static}/images/suckless-ogl/reference_image.webp)
*<center>Le rendu final : 100 sphères métalliques et diélectriques, éclairées par une [HDR](#glossary-hdr "High Dynamic Range — valeurs de couleur supérieures à 1.0 (lumière réaliste)") d'environnement, avec post-processing complet.</center>*

---

## Introduction

[**suckless-ogl**](https://github.com/yoyonel/suckless-ogl) est un moteur de rendu [PBR](#glossary-pbr "Physically-Based Rendering — modèle d'éclairage qui simule la physique réelle de la lumière") (Physically-Based Rendering) minimaliste et performant, écrit en **C11** avec **OpenGL 4.4 Core Profile**. Il affiche une grille de **100 sphères** aux matériaux variés (métaux, diélectriques, peintures, organiques…) éclairées par **Image-Based Lighting** ([IBL](#glossary-ibl "Image-Based Lighting — éclairage extrait d'une image panoramique HDR de l'environnement")), avec un pipeline de post-processing complet : [bloom](#glossary-bloom "Effet de halo lumineux autour des zones très brillantes (diffusion lumineuse de l'objectif)"), [depth of field](#glossary-depth-of-field-dof "Profondeur de champ — flou des objets hors de la distance de mise au point"), [motion blur](#glossary-motion-blur "Flou de mouvement par pixel simulant l'obturateur d'une caméra"), [FXAA](#glossary-fxaa "Fast Approximate Anti-Aliasing — anti-crénelage rapide en post-process sur l'image finale"), [tone mapping](#glossary-tonemapping "Conversion des couleurs HDR (illimitées) en LDR affichable (0–255)"), [color grading](#glossary-color-grading "Ajustement créatif des couleurs (saturation, contraste, gamma, teinte)")…

Cet article retrace le **cycle de vie complet** de l'application : depuis le premier octet alloué dans `main()` jusqu'au moment où le GPU présente la première frame complètement éclairée à l'écran. On va traverser **chaque couche** — mémoire CPU, ressources GPU, la poignée de main X11/GLFW, la création du contexte OpenGL, la compilation des shaders, le [chargement asynchrone](#glossary-chargement-asynchrone "Exécuter les I/O disque sur un thread séparé pour ne pas bloquer le rendu") de textures, et l'architecture de rendu multi-pass qui produit chaque frame.

### Ce qu'on va couvrir

| Chapitre | Sujet |
|----------|-------|
| [1](#chapitre-1-le-point-dentree) | [Le point d'entrée (`main()`)](#chapitre-1-le-point-dentree) |
| [2](#chapitre-2-ouvrir-une-fenetre-glfw-x11-opengl) | [Ouverture de fenêtre (GLFW + X11 + OpenGL)](#chapitre-2-ouvrir-une-fenetre-glfw-x11-opengl) |
| [3](#chapitre-3-initialisation-cote-cpu) | [Initialisation CPU (caméra, threads, buffers)](#chapitre-3-initialisation-cote-cpu) |
| [4](#chapitre-4-initialisation-de-la-scene-le-gpu-se-reveille) | [Initialisation de la scène (GPU)](#chapitre-4-initialisation-de-la-scene-le-gpu-se-reveille) |
| [5](#chapitre-5-setup-du-pipeline-de-post-processing) | [Pipeline de post-processing](#chapitre-5-setup-du-pipeline-de-post-processing) |
| [6](#chapitre-6-le-premier-chargement-hdr) | [Chargement HDR asynchrone](#chapitre-6-le-premier-chargement-hdr) |
| [7](#chapitre-7-generation-ibl-progressive-multi-frame) | [Génération IBL progressive](#chapitre-7-generation-ibl-progressive-multi-frame) |
| [8](#chapitre-8-la-boucle-principale) | [La boucle principale](#chapitre-8-la-boucle-principale) |
| [9](#chapitre-9-le-rendu-dune-frame) | [Le rendu d'une frame](#chapitre-9-le-rendu-dune-frame) |
| [10](#chapitre-10-pipeline-de-post-processing) | [Post-processing en détail](#chapitre-10-pipeline-de-post-processing) |
| [11](#chapitre-11-la-premiere-frame-visible) | [La première frame visible](#chapitre-11-la-premiere-frame-visible) |
| [12](#chapitre-12-budget-memoire-gpu) | [Budget mémoire GPU](#chapitre-12-budget-memoire-gpu) |

---

## Chapitre 1 — Le point d'entrée

Tout commence dans `main()` ([src/main.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/main.c)) :

```c
int main(int argc, char* argv[])
{
    tracy_manager_init_global();          // 1. Bootstrap du profiler

    CliAction action = cli_handle_args(argc, argv);  // 2. Parsing CLI
    if (action == CLI_ACTION_EXIT_SUCCESS) return EXIT_SUCCESS;
    if (action == CLI_ACTION_EXIT_FAILURE) return EXIT_FAILURE;

    // 3. Allocation SIMD-aligned de la structure App
    App* app = (App*)platform_aligned_alloc(sizeof(App), SIMD_ALIGNMENT);
    *app = (App){0};

    // 4. Initialisation complète
    if (!app_init(app, WINDOW_WIDTH, WINDOW_HEIGHT, "Icosphere Phong"))
        { app_cleanup(app); platform_aligned_free(app); return EXIT_FAILURE; }

    // 5. Boucle principale
    app_run(app);

    // 6. Nettoyage
    app_cleanup(app);
    platform_aligned_free(app);
    return EXIT_SUCCESS;
}
```

Le design est **volontairement simple** — toute la complexité est encapsulée dans `app_init()` → `app_run()` → `app_cleanup()`.

### Décisions de design

| Décision | Pourquoi ? |
|----------|-----------|
| **Allocation alignée [SIMD](#glossary-simd "Single Instruction, Multiple Data — calcul vectoriel (1 instruction traite 4+ valeurs)")** | La structure `App` contient des `mat4`/`vec3` (via *[cglm](#glossary-cglm "Bibliothèque C de maths 3D optimisée SIMD (matrices, vecteurs, quaternions)")*) qui bénéficient de l'alignement 16 octets pour la vectorisation [SSE](#glossary-sse "Extensions SIMD d'Intel/AMD pour le x86 (registres 128-bit)")/[NEON](#glossary-neon "Extensions SIMD d'ARM (smartphones, Apple Silicon, Raspberry Pi)") |
| **[Zero-init](#glossary-zero-init "Initialisation à zéro d'une structure C via {0} — garantit un état déterministe au démarrage")** `{0}` | État déterministe — chaque pointeur commence à `NULL`, chaque flag à `0` |
| **[Tracy](#glossary-tracy "Profiler temps réel pour jeux et applis graphiques (mesure CPU + GPU par frame)") en premier** | Le profiler doit être initialisé avant tout autre sous-système pour capturer la timeline complète |
| **Un seul `App` struct** | Tout l'état applicatif vit dans une allocation contiguë — [cache-friendly](#glossary-cache-friendly "Organisation mémoire qui minimise les cache-miss CPU (données contiguës)"), facile à passer |

<pre class="mermaid">
graph TD
    A("🚀 main()") --> B("app_init()")
    B --> B1("Fenêtre + Contexte OpenGL")
    B --> B2("Caméra & Entrées")
    B --> B3("Scène — Ressources GPU")
    B --> B4("Thread de chargement async")
    B --> B5("Pipeline Post-Processing")
    B --> B6("Systèmes de profiling")
    B1 & B2 & B3 & B4 & B5 & B6 --> C("app_run() — Boucle principale")
    C --> C1("Poll Events")
    C1 --> C2("Physique caméra")
    C2 --> C3("renderer_draw_frame()")
    C3 --> C4("SwapBuffers")
    C4 -->|"frame suivante"| C1
    C --> D("app_cleanup()")
    D --> E("🏁 Fin")

    classDef entryExit fill:#fce4ec,stroke:#c2185b,stroke-width:2.5px,color:#2d2d2d
    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444
    classDef loopNode fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d

    class A,E entryExit
    class B,C,D keyFunc
    class B1,B2,B3,B4,B5,B6 subsystem
    class C1,C2,C3,C4 loopNode
</pre>

---

## Chapitre 2 — Ouvrir une fenêtre ([GLFW](#glossary-glfw "Bibliothèque C pour créer des fenêtres et gérer les entrées clavier/souris") + [X11](#glossary-x11 "Système de fenêtrage historique de Linux (serveur d'affichage)") + [OpenGL](#glossary-opengl-44 "API graphique bas-niveau pour communiquer avec le GPU"))

Le premier vrai travail se fait dans `window_create()` ([src/window.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/window.c)).

### 2.1 — Initialisation [GLFW](#glossary-glfw "Bibliothèque C pour créer des fenêtres et gérer les entrées clavier/souris") et [Window Hints](#glossary-window-hints "Paramètres GLFW configurés avant la création de la fenêtre (version OpenGL, profil, MSAA…)")

```c
glfwInit();
glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 4);
glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 4);          // OpenGL 4.4
glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
glfwWindowHint(GLFW_OPENGL_DEBUG_CONTEXT, GL_TRUE);     // Messages de debug
glfwWindowHint(GLFW_SAMPLES, DEFAULT_SAMPLES);           // MSAA = 1 (désactivé)
```

En coulisses, [GLFW](#glossary-glfw "Bibliothèque C pour créer des fenêtres et gérer les entrées clavier/souris") effectue un **handshake [X11](#glossary-x11 "Système de fenêtrage historique de Linux (serveur d'affichage)")** complet :

<pre class="mermaid">
sequenceDiagram
    participant App as Application
    participant GLFW as GLFW
    participant X11 as Serveur X11
    participant Mesa as Mesa/Driver GPU
    participant GPU as GPU

    App->>GLFW: glfwInit()
    GLFW->>X11: XOpenDisplay()
    X11-->>GLFW: Display* (connexion)

    App->>GLFW: glfwCreateWindow(1920, 1080)
    GLFW->>X11: XCreateWindow() + GLX setup
    X11->>Mesa: glXCreateContextAttribsARB(4.4 Core, Debug)
    Mesa->>GPU: Allocation command buffer + état contexte
    Mesa-->>X11: GLXContext
    X11-->>GLFW: Fenêtre + Contexte prêts

    App->>GLFW: glfwMakeContextCurrent()
    GLFW->>Mesa: glXMakeCurrent()
    Mesa->>GPU: Bind du contexte au thread appelant
</pre>

### 2.2 — GLAD : chargement des pointeurs de fonctions OpenGL

```c
gladLoadGLLoader((GLADloadproc)glfwGetProcAddress);
```

OpenGL n'est **pas une bibliothèque** au sens classique — c'est une *spécification*. Les adresses réelles des fonctions vivent dans le driver GPU ([Mesa](#glossary-mesa "Implémentation open-source des API graphiques (OpenGL, Vulkan) sous Linux"), NVIDIA, AMD). [GLAD](#glossary-glad "Générateur de loader OpenGL — résout les adresses des fonctions GL au runtime") interroge chaque adresse à l'exécution via `glXGetProcAddress` et remplit une table de pointeurs de fonctions. Après cet appel, `glCreateShader`, `glDispatchCompute`, etc. deviennent utilisables.

### 2.3 — Contexte debug OpenGL

```c
setup_opengl_debug();
```

Cela active `GL_DEBUG_OUTPUT_SYNCHRONOUS` et enregistre un callback qui intercepte chaque erreur, warning et hint de performance GL. Une table de hachage déduplique les messages (log uniquement à la première occurrence).

### 2.4 — Capture d'entrées et VSync

```c
glfwSwapInterval(0);                    // VSync OFF — FPS illimité
glfwSetInputMode(app->window, GLFW_CURSOR, GLFW_CURSOR_DISABLED);  // Mode FPS
```

Le curseur est capturé en **mode relatif** — les mouvements souris produisent des deltas pour le [contrôle orbital](#glossary-camera-orbitale "Contrôle caméra qui tourne autour d'un point d'intérêt via yaw/pitch depuis les mouvements souris") de la caméra.

---

## Chapitre 3 — Initialisation côté CPU

Avant de toucher au GPU, plusieurs systèmes CPU sont initialisés.

### 3.1 — La caméra orbitale

```c
camera_init(&app->camera, 20.0F, -90.0F, 0.0F);
```

La caméra démarre à :

- **Distance** : 20 unités de l'origine
- **[Yaw](#glossary-yaw---pitch "Yaw = rotation gauche-droite, Pitch = rotation haut-bas de la caméra")** : −90° (regarde le long de −Z)
- **[Pitch](#glossary-yaw---pitch "Yaw = rotation gauche-droite, Pitch = rotation haut-bas de la caméra")** : 0° (niveau de l'horizon)
- **[FOV](#glossary-fov "Field of View — angle de vision de la caméra (60° ici)")** : 60° vertical
- **[Z-clip](#glossary-z-clip "Plans de découpage proche et lointain de la caméra — définissent la plage de profondeur visible")** : [0.1, 1000.0]

Elle utilise un **modèle [physique à pas fixe](#glossary-pas-fixe-fixed-timestep "Mise à jour de la physique à intervalle constant (ex: 60 Hz) indépendamment du framerate")** (60 Hz) avec lissage exponentiel pour la rotation :

<pre class="mermaid">
graph LR
    subgraph "Pipeline de mise à jour caméra"
        A("Delta souris") -->|"Filtre EMA"| B("yaw_target / pitch_target")
        B -->|"Lerp α=0.1"| C("yaw / pitch (lissés)")
        C --> D("camera_update_vectors()")
        D --> E("vecteurs front, right, up")
        E --> F("Matrice de vue (lookAt)")
    end

    subgraph "Physique (60Hz fixe)"
        G("Touches ZQSD") --> H("Vélocité cible")
        H -->|"accélération × dt"| I("Vélocité courante")
        I -->|"friction"| J("Position += vel × dt")
        J --> K("Head bobbing (sin)")
    end

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444
    classDef loopNode fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d

    class D,F keyFunc
    class A,B,C,E subsystem
    class G,H,I,J,K loopNode
</pre>

### 3.2 — Thread de chargement asynchrone

```c
app->async_loader = async_loader_create(&app->tracy_mgr);
```

Un **[thread POSIX](#glossary-posix-threads "API standard de threads sur Unix/Linux (`pthread_create`, `pthread_cond_wait`)") dédié** est créé pour les I/O en arrière-plan. Il dort sur une [variable de condition](#glossary-variable-de-condition "Mécanisme de synchronisation : un thread dort jusqu'à ce qu'un autre le réveille") (`pthread_cond_wait`) jusqu'à ce qu'un travail soit soumis. Cela empêche les lectures disque de bloquer la boucle de rendu.

<pre class="mermaid">
stateDiagram-v2
    [*] --> IDLE
    IDLE --> PENDING: async_loader_request()
    PENDING --> LOADING: Le worker se réveille
    LOADING --> WAITING_FOR_PBO: I/O terminée, besoin d'un buffer GPU
    WAITING_FOR_PBO --> CONVERTING: Le thread principal fournit le PBO
    CONVERTING --> READY: Conversion SIMD Float→Half terminée
    READY --> IDLE: Le thread principal consomme le résultat
</pre>

---

## Chapitre 4 — Initialisation de la scène (le GPU se réveille)

`scene_init()` ([src/scene.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/scene.c)) est l'endroit où le GPU reçoit son premier vrai travail.

### 4.1 — État initial de la scène

```c
scene->subdivisions    = 3;                     // Icosphère niveau 3
scene->wireframe       = 0;                     // Remplissage solide
scene->show_envmap     = 1;                     // Skybox visible
scene->billboard_mode  = 1;                     // Sphères transparentes (billboard)
scene->sorting_mode    = SORTING_MODE_GPU_BITONIC;  // Tri GPU
scene->gi_mode         = GI_MODE_OFF;           // Pas de GI
scene->specular_aa_enabled = 1;                 // AA basé sur la courbure
```

### 4.2 — Textures factices et BRDF LUT

Deux textures sentinelles sont créées immédiatement — elles servent de **fallback** tant qu'une texture [IBL](#glossary-ibl "Image-Based Lighting — éclairage extrait d'une image panoramique HDR de l'environnement") n'est pas prête :

```c
scene->dummy_black_tex = render_utils_create_color_texture(0.0, 0.0, 0.0, 0.0);  // 1×1 RGBA
scene->dummy_white_tex = render_utils_create_color_texture(1.0, 1.0, 1.0, 1.0);  // 1×1 RGBA
```

Puis la **[BRDF LUT](#glossary-brdf-lut "Texture pré-calculée qui encode l'intégrale BRDF pour toutes les combinaisons (angle, rugosité)")** (Look-Up Table) est générée une seule fois via [compute shader](#glossary-compute-shader "Shader généraliste pour du calcul GPU hors pipeline de rendu") :

```c
scene->brdf_lut_tex = build_brdf_lut_map(512);
```

| Propriété | Valeur |
|-----------|--------|
| Taille | 512 × 512 |
| Format | `GL_RG16F` (2 canaux, 16-bit float chacun) |
| Contenu | [BRDF](#glossary-brdf "Bidirectional Reflectance Distribution Function — fonction décrivant comment la lumière rebondit sur une surface") split-sum pré-intégrée ([Fresnel-Schlick](#glossary-fresnel-schlick "Approximation de l'effet Fresnel : les surfaces reflètent plus en angle rasant")–[GGX](#glossary-ggx---smith-ggx "Modèle de micro-facettes pour la géométrie et distribution des normales (rugosité)")) |
| [Shader](#glossary-shader "Programme exécuté directement sur le GPU (vertex, fragment, compute)") | `shaders/IBL/spbrdf.glsl` ([compute](#glossary-compute-shader "Shader généraliste pour du calcul GPU hors pipeline de rendu")) |
| [Work groups](#glossary-work-group "Groupe de threads GPU exécutés ensemble dans un compute shader (ex: 16×16 = 256 threads)") | 16 × 16 (512/32 par axe) |

Cette texture mappe `(NdotV, roughness)` → `(F0_scale, F0_bias)` et est utilisée chaque frame par le [fragment shader](#glossary-fragment-shader "Shader qui calcule la couleur de chaque pixel à l'écran") [PBR](#glossary-pbr "Physically-Based Rendering — modèle d'éclairage qui simule la physique réelle de la lumière") pour éviter l'intégration [BRDF](#glossary-brdf "Bidirectional Reflectance Distribution Function — fonction décrivant comment la lumière rebondit sur une surface") coûteuse en temps réel.

### 4.3 — Deux modes de rendu : Billboard Ray-Tracing vs. Mesh Icosphère

Le moteur supporte deux stratégies de rendu de sphères. Le **mode par défaut** est le [billboard](#glossary-billboard "Quad (rectangle) toujours face à la caméra, utilisé ici comme surface de ray-tracing") [ray-tracing](#glossary-ray-tracing "Technique qui trace des rayons lumineux pour calculer l'intersection avec des objets").

#### Mode par défaut : Billboard + Ray-Tracing par pixel (billboard_mode = 1)

Chaque sphère est rendue comme un **simple [quad](#glossary-quad "Rectangle composé de 2 triangles — la primitive 2D de base") aligné à l'écran** (4 vertices, 2 triangles). Le fragment [shader](#glossary-shader "Programme exécuté directement sur le GPU (vertex, fragment, compute)") effectue une **intersection rayon-sphère analytique** par pixel, produisant des sphères mathématiquement parfaites.

![Géométrie AABB du billboard — le quad projeté enveloppe la sphère à l'écran]({static}/images/suckless-ogl/billboard_aabb_geometry.webp)
*<center>Le [vertex shader](#glossary-vertex-shader "Shader qui traite chaque sommet de la géométrie (position, projection)") projette un quad serré autour de la [bounding box](#glossary-aabb "Axis-Aligned Bounding Box — boîte englobante alignée aux axes, pour le culling rapide") à l'écran de la sphère via calcul de tangentes analytiques.</center>*

**Avantages** :

- Silhouettes parfaites au pixel près (jamais de facettage polygonal)
- Profondeur correcte par pixel (`gl_FragDepth` écrit depuis le point d'intersection)
- [Normales](#glossary-normale "Vecteur perpendiculaire à la surface en un point — détermine l'orientation de la surface") analytiquement lisses (normalisé `hitPos − center`)
- [Anti-aliasing](#glossary-anti-aliasing "Technique de lissage des bords en escalier (aliasing) pour un rendu visuellement plus propre") des bords via atténuation douce du [discriminant](#glossary-discriminant "Valeur mathématique (b²−c) déterminant si un rayon touche une sphère")
- Vraie transparence alpha (aspect verre, avec tri [back-to-front](#glossary-back-to-front "Ordre de rendu du plus loin au plus proche, nécessaire pour la transparence correcte"))

<pre class="mermaid">
graph LR
    subgraph "Billboard Ray-Tracing (Défaut)"
        A("Quad 4-vertex<br/>(par instance)") -->|"Vertex Shader :<br/>projection sur bounds sphère"| B("Quad écran")
        B -->|"Fragment Shader :<br/>intersection rayon-sphère"| C("Sphère parfaite<br/>normale + profondeur par pixel")
    end

    subgraph "Mesh Icosphère (Fallback)"
        D("Mesh 642-vertex<br/>(icosaèdre subdivisé)") -->|"Rastérisé en<br/>triangles"| E("Approximation polygonale<br/>(facettée à basse subdiv)")
    end

    classDef highlight fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef fallback fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#666666

    class A,B,C highlight
    class D,E fallback
</pre>

> **💡 Pourquoi le [billboard](#glossary-billboard "Quad (rectangle) toujours face à la caméra, utilisé ici comme surface de ray-tracing") ray-tracing ?** Avec 100 sphères, l'approche billboard utilise **100 × 4 = 400 vertices** au total, versus **100 × 642 = 64 200 vertices** pour des [icosphères](#glossary-icosphre "Sphère construite en subdivisant un icosaèdre (20 faces) — plus uniforme qu'une UV sphere") niveau 3. Plus important encore, les sphères sont **mathématiquement parfaites** à tout niveau de zoom — aucun artefact de [tessellation](#glossary-tessellation "Subdivision de la géométrie en triangles plus fins pour plus de détail").

#### Fallback : Mesh icosphère instancié (billboard_mode = 0)

Le chemin [icosphère](#glossary-icosphre "Sphère construite en subdivisant un icosaèdre (20 faces) — plus uniforme qu'une UV sphere") génère un [icosaèdre](#glossary-icosphre "Sphère construite en subdivisant un icosaèdre (20 faces) — plus uniforme qu'une UV sphere") subdivisé récursivement :

<pre class="mermaid">
graph LR
    A("Niveau 0<br/>12 vertices<br/>20 triangles") -->|"Subdiviser"| B("Niveau 1<br/>42 vertices<br/>80 triangles")
    B -->|"Subdiviser"| C("Niveau 2<br/>162 vertices<br/>320 triangles")
    C -->|"Subdiviser"| D("Niveau 3<br/>642 vertices<br/>1 280 triangles")
    D -->|"..."| E("Niveau 6<br/>~40k vertices")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class D keyFunc
    class A,B,C,E subsystem
</pre>

### 4.4 — Bibliothèque de matériaux

```c
scene->material_lib = material_load_presets("assets/materials/pbr_materials.json");
```

Le fichier [JSON](#glossary-json "JavaScript Object Notation — format de fichier texte léger pour stocker des données structurées (clé/valeur)") définit **101 matériaux [PBR](#glossary-pbr "Physically-Based Rendering — modèle d'éclairage qui simule la physique réelle de la lumière")** organisés par catégorie :

| Catégorie | Exemples | Métallicité | Rugosité |
|-----------|----------|-------------|----------|
| **Métaux purs** | Or, Argent, Cuivre, Chrome | 1.0 | 0.05–0.2 |
| **Métaux vieillis** | Fer rouillé, Cuivre oxydé | 0.7–0.95 | 0.4–0.8 |
| **[Diélectriques](#glossary-dilectrique "Matériau non-métallique (plastique, verre, bois) — reflète peu à angle direct") brillants** | Plastiques colorés | 0.0 | 0.05–0.15 |
| **Matériaux mats** | Tissu, Argile, Sable | 0.0 | 0.65–0.95 |
| **Pierres** | Granit, Marbre, Obsidienne | 0.0 | 0.35–0.85 |
| **Organiques** | Chêne, Cuir, Os | 0.0 | 0.35–0.75 |
| **Peintures** | Carrosserie, Nacré, Satin | 0.3–0.7 | 0.1–0.5 |
| **Techniques** | Caoutchouc, Carbone, Céramique | 0.0–0.1 | 0.05–0.85 |

Chaque matériau fournit : [`albedo`](#glossary-albedo "Couleur de base d'un matériau (sans éclairage)") (RGB), [`metallic`](#glossary-metallic "Paramètre PBR : 0 = diélectrique (plastique, bois), 1 = métal (or, chrome)") (0–1), [`roughness`](#glossary-roughness "Paramètre PBR : 0 = miroir parfait, 1 = complètement mat") (0–1).

### 4.5 — La grille d'instances

```c
const int cols    = 10;       // DEFAULT_COLS
const float spacing = 2.5F;   // DEFAULT_SPACING
```

Une **grille 10×10 de 100 sphères** est disposée dans le plan XY, centrée à l'origine :

```
Dimensions de la grille :
  Largeur = (10 - 1) × 2.5 = 22.5 unités
  Hauteur = (10 - 1) × 2.5 = 22.5 unités
  Z = 0 (toutes les sphères dans le même plan)
```

Chaque instance stocke **88 octets** :

```c
typedef struct SphereInstance {
    mat4  model;      // 64 octets — matrice de transformation 4×4
    vec3  albedo;     // 12 octets — couleur RGB
    float metallic;   //  4 octets
    float roughness;  //  4 octets
    float ao;         //  4 octets — toujours 1.0
} SphereInstance;     // Total : 88 octets par instance
```

### 4.6 — Layout du VAO (mode billboard)

En mode billboard, le [VAO](#glossary-vao "Vertex Array Object — décrit le format des données géométriques envoyées au GPU") lie un **quad de 4 vertices** et les données matériaux par instance :

```
┌────────────────────────────────────────────────────────────────┐
│              Billboard VAO (Mode de rendu par défaut)          │
├────────────┬────────────┬─────────────────────────────────────┤
│  Location  │  Source    │  Description                        │
├────────────┼────────────┼─────────────────────────────────────┤
│  0         │  Quad VBO  │  vec3 position   (±0.5 quad verts)  │
│  1         │  Quad VBO  │  vec3 normale    (stub, inutilisé)  │
│  2–5       │  Inst VBO  │  mat4 modèle     (par instance)     │
│  6         │  Inst VBO  │  vec3 albedo     (par instance)     │
│  7         │  Inst VBO  │  vec3 pbr (M,R,AO) (par instance)   │
└────────────┴────────────┴─────────────────────────────────────┘

Location 0–1 : glVertexAttribDivisor = 0 (avance par vertex, 4 verts)
Location 2–7 : glVertexAttribDivisor = 1 (avance par instance)
```

**Appel de [draw](#glossary-draw-call "Un appel CPU→GPU qui demande le rendu d'un jeu de géométrie")** : `glDrawArraysInstanced(GL_TRIANGLE_STRIP, 0, 4, 100)` — 100 quads, [face culling](#glossary-face-culling "Optimisation GPU qui élimine les triangles dont la face arrière est visible — désactivé ici pour les billboards") désactivé.

### 4.7 — Compilation des shaders

Tous les shaders sont compilés pendant `scene_init()`. Le loader ([src/shader.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/shader.c)) supporte un système d'inclusion **`@header`** personnalisé :

```glsl
// Dans pbr_ibl_instanced.frag :
@header "pbr_functions.glsl"
@header "sh_probe.glsl"
```

Ce système inline récursivement les fichiers (profondeur max : 16), avec déduplication type [include-guard](#glossary-include-guard "Mécanisme de déduplication qui empêche un fichier d'être inclus plusieurs fois").

<pre class="mermaid">
graph TD
    INIT("scene_init() — Compilation des shaders") --> REND
    INIT --> COMP
    INIT --> POST

    subgraph REND ["🎨 Programmes de rendu"]
        direction TB
        PBR("PBR Instancié — pbr_ibl_instanced.vert/.frag")
        BB("PBR Billboard — pbr_ibl_billboard.vert/.frag")
        SKY("Skybox — background.vert/.frag")
        UI("UI Overlay — ui.vert/.frag")
    end

    subgraph COMP ["⚡ Compute Shaders"]
        direction TB
        SPMAP("Prefiltre Spéculaire — IBL/spmap.glsl")
        IRMAP("Conv. Irradiance — IBL/irmap.glsl")
        BRDF("BRDF LUT — IBL/spbrdf.glsl")
        LUM("Réduction Luminance — IBL/luminance_reduce")
    end

    subgraph POST ["✨ Post-Process"]
        direction TB
        PP("Composite Final — postprocess.vert/.frag")
        BL("Bloom — down/up/prefilter")
    end

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef render fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef compute fill:#f3e5f5,stroke:#ab47bc,stroke-width:1.5px,color:#2d2d2d
    classDef postfx fill:#fce4ec,stroke:#c2185b,stroke-width:1.5px,color:#2d2d2d

    class INIT keyFunc
    class PBR,BB,SKY,UI render
    class SPMAP,IRMAP,BRDF,LUM compute
    class PP,BL postfx
</pre>

---

## Chapitre 5 — Setup du pipeline de post-processing

```c
postprocess_init(&app->postprocess, &app->gpu_profiler, 1920, 1080);
```

### 5.1 — Le FBO de scène (Multi-Render Target)

Le [framebuffer offscreen](#glossary-fbo "Framebuffer Object — surface de rendu offscreen (on dessine dedans au lieu de l'écran)") principal utilise le **[MRT](#glossary-mrt "Multiple Render Targets — écrire dans plusieurs textures en une seule passe de rendu")** (Multiple Render Targets) :

| Attachment | Format | Taille | Rôle |
|-----------|--------|--------|------|
| `GL_COLOR_ATTACHMENT0` | `GL_RGBA16F` | 1920×1080 | Couleur [HDR](#glossary-hdr "High Dynamic Range — valeurs de couleur supérieures à 1.0 (lumière réaliste)") de la scène (alpha = [luma](#glossary-luma "Approximation rapide de la luminance perçue (0.299R + 0.587G + 0.114B) — utilisée par FXAA pour détecter les bords") pour [FXAA](#glossary-fxaa "Fast Approximate Anti-Aliasing — anti-crénelage rapide en post-process sur l'image finale")) |
| `GL_COLOR_ATTACHMENT1` | `GL_RG16F` | 1920×1080 | Vélocité par pixel pour le [motion blur](#glossary-motion-blur "Flou de mouvement par pixel simulant l'obturateur d'une caméra") |
| `GL_DEPTH_STENCIL_ATTACHMENT` | `GL_DEPTH32F_STENCIL8` | 1920×1080 | Buffer de [profondeur](#glossary-z-buffer---depth-buffer "Texture qui stocke la profondeur de chaque pixel pour gérer l'occlusion") + masque [stencil](#glossary-stencil-buffer "Masque par pixel permettant de restreindre le rendu à certaines zones") |
| [Stencil view](#glossary-texture-view "Vue alternative sur les données d'une texture existante (format ou couches différents)") | `GL_R8UI` | 1920×1080 | [Stencil](#glossary-stencil-buffer "Masque par pixel permettant de restreindre le rendu à certaines zones") en lecture seule comme texture |

<pre class="mermaid">
graph TD
    FBO("FBO de Scène — Multi-Render Target") --> C0
    FBO --> C1
    FBO --> DS
    DS --> SV

    C0("🟦 Color 0 — GL_RGBA16F<br/>Couleur HDR scène")
    C1("🟩 Color 1 — GL_RG16F<br/>Vecteurs vélocité")
    DS("🟫 Depth/Stencil — GL_DEPTH32F_STENCIL8")
    SV("🟪 Vue Stencil — GL_R8UI (TextureView)")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef color0 fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef color1 fill:#e8f5e9,stroke:#66bb6a,stroke-width:1.5px,color:#2d2d2d
    classDef depth fill:#fff3e0,stroke:#ff9800,stroke-width:1.5px,color:#2d2d2d
    classDef stencil fill:#f3e5f5,stroke:#ab47bc,stroke-width:1.5px,color:#2d2d2d

    class FBO keyFunc
    class C0 color0
    class C1 color1
    class DS depth
    class SV stencil
</pre>

### 5.2 — Ressources des sous-effets

Chaque effet de post-processing initialise ses propres ressources :

| Effet | Ressources GPU |
|-------|---------------|
| **[Bloom](#glossary-bloom "Effet de halo lumineux autour des zones très brillantes (diffusion lumineuse de l'objectif)")** | [FBOs](#glossary-fbo "Framebuffer Object — surface de rendu offscreen (on dessine dedans au lieu de l'écran)") [mip](#glossary-mipmap "Versions pré-réduites d'une texture (½, ¼, ⅛…) pour un filtrage plus propre au loin")-chain (6 niveaux), textures [prefilter](#glossary-prefilter "Passe initiale du bloom qui extrait les pixels au-dessus d'un seuil de luminosité")/[downsample](#glossary-downsample "Réduction progressive de la résolution d'une texture (par 2 à chaque niveau)")/[upsample](#glossary-upsample "Agrandissement progressif d'une texture basse résolution vers la résolution originale") |
| **[DoF](#glossary-depth-of-field-dof "Profondeur de champ — flou des objets hors de la distance de mise au point")** | Texture de flou, texture [CoC](#glossary-coc "Circle of Confusion — diamètre du disque de flou d'un point hors focus") (Circle of Confusion) |
| **[Auto-Exposure](#glossary-auto-exposition "Adaptation automatique de la luminosité de la scène (simule l'iris de l'œil)")** | Texture de downsample [luminance](#glossary-luminance "Mesure de l'intensité lumineuse perçue d'une image — utilisée pour l'auto-exposition"), 2× [PBOs](#glossary-pbo "Pixel Buffer Object — buffer pour les transferts asynchrones de pixels CPU↔GPU") (readback), 2× [GLSync fences](#glossary-fence-glsync "Objet de synchronisation GPU — permet d'attendre qu'un travail GPU soit terminé") |
| **[Motion Blur](#glossary-motion-blur "Flou de mouvement par pixel simulant l'obturateur d'une caméra")** | Texture [tile-max velocity](#glossary-tile-max-velocity "Texture intermédiaire qui stocke la vélocité maximale par tuile (ex: 20×20 pixels), pour optimiser le motion blur") ([compute](#glossary-compute-shader "Shader généraliste pour du calcul GPU hors pipeline de rendu")), texture [neighbor-max](#glossary-neighbor-max "Texture qui propage la vélocité max aux tuiles voisines, couvrant le flou de mouvement inter-tuiles") ([compute](#glossary-compute-shader "Shader généraliste pour du calcul GPU hors pipeline de rendu")) |
| **[3D LUT](#glossary-3d-lut "Table 3D de correspondance couleur → couleur pour un &quot;look&quot; cinématique (fichier `.cube`)")** | `GL_TEXTURE_3D` 32³ chargé depuis des fichiers [`.cube`](#glossary-cube-format "Format de fichier texte définissant une LUT 3D de correspondance couleur, standard dans le cinéma et les DCC") |

### 5.3 — Effets actifs par défaut

```c
postprocess_enable(&app->postprocess, POSTFX_FXAA);  // Seulement FXAA
```

Au démarrage, seul **[FXAA](#glossary-fxaa "Fast Approximate Anti-Aliasing — anti-crénelage rapide en post-process sur l'image finale")** est actif. Les autres effets sont activés/désactivés en temps réel via raccourcis clavier.

---

## Chapitre 6 — Le premier chargement HDR

```c
env_manager_load(&app->env_mgr, app->async_loader, "env.hdr");
```

Cela déclenche le **pipeline de [chargement asynchrone](#glossary-chargement-asynchrone "Exécuter les I/O disque sur un thread séparé pour ne pas bloquer le rendu") d'environnement** — l'opération multi-frame la plus complexe du moteur.

### 6.1 — Séquence de chargement async

<pre class="mermaid">
sequenceDiagram
    participant Main as Thread Principal (Rendu)
    participant Worker as Thread Worker Async
    participant GPU as GPU

    Main->>Worker: async_loader_request("env.hdr")
    Note over Worker: État: PENDING → LOADING
    Worker->>Worker: stbi_loadf() — décode HDR en float RGBA
    Note over Worker: ~50ms pour 2K HDR sur NVMe

    Worker-->>Main: État: WAITING_FOR_PBO
    Main->>GPU: glGenBuffers() → PBO
    Main->>GPU: glMapBuffer(PBO, WRITE)
    Main-->>Worker: async_loader_provide_pbo(pbo_ptr)

    Note over Worker: État: CONVERTING
    Worker->>Worker: Conversion SIMD float32 → float16
    Note over Worker: ~2ms pour 2048×1024

    Worker-->>Main: État: READY
    Main->>GPU: glUnmapBuffer(PBO)
    Main->>GPU: glTexSubImage2D(depuis PBO)
    Note over GPU: Transfert DMA : PBO → VRAM
    Main->>GPU: glGenerateMipmap()
</pre>

### 6.2 — Machine à états de transition

Pendant le premier chargement, l'écran reste **noir** (pas de crossfade depuis une scène précédente) :

<pre class="mermaid">
stateDiagram-v2
    [*] --> WAIT_IBL: "Premier chargement"
    WAIT_IBL --> WAIT_IBL: "IBL en cours..."
    WAIT_IBL --> FADE_IN: "IBL terminé"
    FADE_IN --> IDLE: "Alpha atteint 0"
</pre>

**`WAIT_IBL`** : `transition_alpha = 1.0` (noir opaque complet) — l'écran est noir pendant les premières frames.

**`FADE_IN`** : l'alpha diminue de 1.0 → 0.0 sur 250ms.

---

## Chapitre 7 — Génération [IBL](#glossary-ibl "Image-Based Lighting — éclairage extrait d'une image panoramique HDR de l'environnement") (progressive, multi-frame)

Une fois la texture [HDR](#glossary-hdr "High Dynamic Range — valeurs de couleur supérieures à 1.0 (lumière réaliste)") uploadée, le **coordinateur [IBL](#glossary-ibl "Image-Based Lighting — éclairage extrait d'une image panoramique HDR de l'environnement")** ([src/ibl_coordinator.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/ibl_coordinator.c)) prend le relais. Il calcule trois maps sur plusieurs frames pour éviter les [stalls GPU](#glossary-gpu-stall "Blocage du pipeline GPU quand il attend une ressource ou une synchronisation — provoque des chutes de framerate").

### 7.1 — Les trois maps [IBL](#glossary-ibl "Image-Based Lighting — éclairage extrait d'une image panoramique HDR de l'environnement")

<pre class="mermaid">
graph TB
    HDR("Map d'environnement HDR<br/>2048×1024 equirectangulaire<br/>GL_RGBA16F") --> SPEC
    HDR --> IRR
    HDR --> LUM

    SPEC("Map Prefiltre Spéculaire<br/>1024×1024 × 5 niveaux mip<br/>Compute: spmap.glsl")
    IRR("Map d'Irradiance<br/>64×64<br/>Compute: irmap.glsl")
    LUM("Réduction Luminance<br/>1×1 moyenne<br/>Compute: luminance_reduce")

    SPEC -->|"Réflexion par pixel<br/>roughness → niveau mip"| PBR("Shader PBR")
    IRR -->|"Intégrale diffuse<br/>hémisphérique"| PBR
    LUM -->|"Seuil auto-exposure"| PP("Post-Process")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef compute fill:#f3e5f5,stroke:#ab47bc,stroke-width:1.5px,color:#2d2d2d
    classDef target fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d

    class HDR keyFunc
    class SPEC,IRR,LUM compute
    class PBR,PP target
</pre>

| Map | Résolution | Format | Niveaux [Mip](#glossary-mipmap "Versions pré-réduites d'une texture (½, ¼, ⅛…) pour un filtrage plus propre au loin") | [Compute Shader](#glossary-compute-shader "Shader généraliste pour du calcul GPU hors pipeline de rendu") |
|-----|-----------|--------|-------------|----------------|
| **[Prefiltre Spéculaire](#glossary-prefiltre-spculaire "Texture mip-mappée encodant les réflexions floues par niveau de rugosité")** | 1024×1024 | `GL_RGBA16F` | 5 | `IBL/spmap.glsl` |
| **[Irradiance](#glossary-irradiance-map "Texture encodant la lumière ambiante diffuse intégrée sur l'hémisphère pour chaque direction")** | 64×64 | `GL_RGBA16F` | 1 | `IBL/irmap.glsl` |
| **[Luminance](#glossary-luminance "Mesure de l'intensité lumineuse perçue d'une image — utilisée pour l'auto-exposition")** | 1×1 | `GL_R32F` | 1 | `IBL/luminance_reduce_pass1/2.glsl` |

### 7.2 — Stratégie de découpage progressif

Pour éviter les pics de [frame time](#glossary-frame-time "Durée totale de rendu d'une image — 16.6ms à 60 FPS, tout dépassement provoque un saccade"), chaque niveau [mip](#glossary-mipmap "Versions pré-réduites d'une texture (½, ¼, ⅛…) pour un filtrage plus propre au loin") est subdivisé en **slices** traitées sur des frames consécutives :

| Étape [IBL](#glossary-ibl "Image-Based Lighting — éclairage extrait d'une image panoramique HDR de l'environnement") | GPU Hardware | GPU Software ([llvmpipe](#glossary-llvmpipe "Driver OpenGL logiciel de Mesa — émule le GPU entièrement sur CPU via LLVM JIT, utilisé en CI ou sans carte graphique")) |
|-----------|-------------|------------------------|
| Specular Mip 0 (1024²) | 24 slices (42 lignes chacune) | 1 slice (complet) |
| Specular Mip 1 (512²) | 8 slices | 1 slice |
| Specular Mips 2–4 | Groupées (1 dispatch) | 1 slice |
| [Irradiance](#glossary-irradiance-map "Texture encodant la lumière ambiante diffuse intégrée sur l'hémisphère pour chaque direction") (64²) | 12 slices | 1 slice |
| [Luminance](#glossary-luminance "Mesure de l'intensité lumineuse perçue d'une image — utilisée pour l'auto-exposition") | 2 [dispatches](#glossary-dispatch "Appel CPU qui lance un compute shader sur le GPU") (pass 1 + 2) | 2 [dispatches](#glossary-dispatch "Appel CPU qui lance un compute shader sur le GPU") |

<pre class="mermaid">
gantt
    title Timeline de génération IBL progressive
    dateFormat x
    axisFormat Frame %s

    section Luminance
    Luminance Pass 1       :lum1, 0, 1000
    Luminance Wait (fence) :lum2, 1000, 2000
    Luminance Readback     :lum3, 2000, 3000

    section Specular Mip 0
    Slice 1/24             :s1, 3000, 4000
    Slice 2/24             :s2, 4000, 5000
    Slice ...              :s3, 5000, 6000
    Slice 24/24            :s4, 6000, 7000

    section Specular Mip 1
    Slices 1-8             :m1, 7000, 9000

    section Specular Mips 2-4
    Dispatch groupé        :m3, 9000, 10000

    section Irradiance
    Slices 1-12            :i1, 10000, 12000

    section Terminé
    IBL Complet → Fade In  :ibl_done, 12000, 13000
</pre>

### 7.3 — Machine à états IBL

```c
enum IBLState {
    IBL_STATE_IDLE,             // Pas de travail
    IBL_STATE_LUMINANCE,        // Pass 1 : réduction luminance
    IBL_STATE_LUMINANCE_WAIT,   // Attente fence readback
    IBL_STATE_SPECULAR_INIT,    // Allocation texture spéculaire
    IBL_STATE_SPECULAR_MIPS,    // Génération progressive des mips
    IBL_STATE_IRRADIANCE,       // Convolution irradiance progressive
    IBL_STATE_DONE              // Toutes les maps prêtes
};
```

---

## Chapitre 8 — La boucle principale

`app_run()` ([src/app.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/app.c)) est le battement de cœur — une **[boucle de jeu](#glossary-game-loop "Boucle principale d'un jeu : lire les entrées → mettre à jour → dessiner → recommencer") non capée** classique avec [physique à pas fixe](#glossary-pas-fixe-fixed-timestep "Mise à jour de la physique à intervalle constant (ex: 60 Hz) indépendamment du framerate").

<pre class="mermaid">
graph TD
    A("① glfwPollEvents() — Clavier, souris, resize")
    A --> B("② Temps & FPS — delta_time, frame_count")
    B --> C("③ Physique Caméra — Pas fixe 60Hz, lerp rotation")
    C --> D("④ Mise à jour géométrie — si subdiv changé")
    D --> E("⑤ app_update() — Traitement état entrées")
    E --> F("⑥ renderer_draw_frame() — LE GROS MORCEAU")
    F --> G("⑦ Tracy screenshots — profiling")
    G --> H("⑧ glfwSwapBuffers() — Présentation à l'écran")
    H -->|"frame suivante"| A

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef loopNode fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class F keyFunc
    class A,B,C,D,E,G loopNode
    class H subsystem
</pre>

### 8.1 — Resize différé

Les événements de redimensionnement sont **différés** — le callback [GLFW](#glossary-glfw "Bibliothèque C pour créer des fenêtres et gérer les entrées clavier/souris") enregistre seulement les nouvelles dimensions. La recréation réelle des FBOs se fait au début de la frame suivante, hors du contexte limité du callback.

### 8.2 — Intégration caméra à pas fixe

```c
app->camera.physics_accumulator += (float)app->delta_time;
while (app->camera.physics_accumulator >= app->camera.fixed_timestep) {
    camera_fixed_update(&app->camera);  // Vélocité, friction, bobbing
    app->camera.physics_accumulator -= app->camera.fixed_timestep;
}

// Rotation lissée (interpolation exponentielle)
float alpha = app->camera.rotation_smoothing;  // ~0.1
app->camera.yaw   += (app->camera.yaw_target   - app->camera.yaw)   * alpha;
app->camera.pitch += (app->camera.pitch_target - app->camera.pitch) * alpha;
camera_update_vectors(&app->camera);
```

Cela garantit une physique déterministe indépendamment du framerate, tandis que la rotation reste fluide via interpolation par frame.

---

## Chapitre 9 — Le rendu d'une frame

`renderer_draw_frame()` ([src/renderer.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/renderer.c)) orchestre le pipeline de rendu complet.

### 9.1 — Architecture haut niveau

<pre class="mermaid">
graph TD
    A("GPU Profiler Begin") --> B("postprocess_begin() — Bind Scene FBO, Clear")
    B --> C("camera_get_view_matrix()")
    C --> D("glm_perspective() — FOV=60°, near=0.1, far=1000")
    D --> E("ViewProj = Proj × View")
    E --> G1("🌅 Pass 1 : Skybox — depth désactivée")
    G1 --> G2("🔢 Pass 2 : Tri des sphères — GPU Bitonic")
    G2 --> G3("🔮 Pass 3 : Sphères PBR — draw instancié billboard")
    G3 --> H("✨ postprocess_end() — Pipeline 7 étapes")
    H --> I("🖥️ UI Overlay + Transition Env")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef loopNode fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef setup fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444
    classDef postfx fill:#fce4ec,stroke:#c2185b,stroke-width:1.5px,color:#2d2d2d

    class G1,G2,G3 keyFunc
    class A,B,C,D,E setup
    class H,I postfx
</pre>

### 9.2 — Pass 1 : Skybox

La [skybox](#glossary-skybox "Image panoramique affichée en fond de scène comme ciel/environnement") est dessinée **en premier**, avec le test de profondeur **désactivé**. Elle utilise une astuce de [quad](#glossary-quad "Rectangle composé de 2 triangles — la primitive 2D de base") plein écran :

```glsl
// background.vert — reconstruction du rayon en espace monde
gl_Position = vec4(in_position.xy, 1.0, 1.0);  // Depth = 1.0 (plan lointain)
vec4 pos = m_inv_view_proj * vec4(in_position.xy, 1.0, 1.0);
RayDir = pos.xyz / pos.w;  // Rayon espace monde reconstruit
```

```glsl
// background.frag — échantillonnage equirectangulaire de la HDR
vec2 uv = SampleEquirectangular(normalize(RayDir));
vec3 envColor = textureLod(environmentMap, uv, blur_lod).rgb;
envColor = clamp(envColor, vec3(0.0), vec3(200.0));  // Protection NaN + anti-fireflies
FragColor = vec4(envColor, luma);  // Alpha = luma pour FXAA
VelocityOut = vec2(0.0);          // Pas de mouvement pour la skybox
```

### 9.3 — Pass 2 : Tri des sphères (Bitonic Sort GPU)

Pour le rendu transparent par [billboard](#glossary-billboard "Quad (rectangle) toujours face à la caméra, utilisé ici comme surface de ray-tracing"), les sphères doivent être dessinées **back-to-front** :

| Mode | Où | Algorithme | Complexité |
|------|-----|-----------|------------|
| `CPU_QSORT` | CPU | `qsort()` (stdlib) | O(n·log n) moy |
| `CPU_RADIX` | CPU | [Tri radix](#glossary-radix-sort "Tri par chiffres successifs — O(n·k), efficace sur CPU pour des clés entières") | O(n·k) |
| `GPU_BITONIC` ★ | GPU | [Tri bitonique](#glossary-bitonic-sort "Tri parallèle adapté au GPU — compare et échange par paires") (compute) | O(n·log²n) |

### 9.4 — Pass 3 : Sphères PBR — Billboard Ray-Tracing

C'est le cœur du rendu. **Un seul appel de draw rend les 100 sphères** :

| Métrique | Valeur |
|----------|--------|
| Vertices par sphère | **4** (quad billboard) |
| Triangles par sphère | 2 (triangle strip) |
| Instances | 100 (grille 10×10) |
| **Total vertices** | **400** |
| **Draw calls** | **1** |
| Précision sphère | **Mathématiquement parfaite** (ray-tracée) |

### 9.5 — Le fragment shader billboard (intersection rayon-sphère)

Le [fragment shader](#glossary-fragment-shader "Shader qui calcule la couleur de chaque pixel à l'écran") (`pbr_ibl_billboard.frag`) est là où la magie opère. Au lieu de [shader](#glossary-shader "Programme exécuté directement sur le GPU (vertex, fragment, compute)") un [mesh](#glossary-mesh "Ensemble de triangles formant un objet 3D") rastérisé, il **intersecte analytiquement un rayon avec une sphère parfaite** :

![Intersection rayon-sphère — le principe géométrique]({static}/images/suckless-ogl/sphere_intersection.webp)
*<center>Intersection rayon-sphère analytique : le [discriminant](#glossary-discriminant "Valeur mathématique (b²−c) déterminant si un rayon touche une sphère") détermine si le pixel touche la sphère.</center>*

```glsl
// Intersection rayon-sphère analytique
vec3 oc = rayOrigin - center;
float b = dot(oc, rayDir);
float c = dot(oc, oc) - radius * radius;
float discriminant = b * b - c;  // >0 = touché, <0 = raté
if (discriminant < 0.0) discard;
float t = -b - sqrt(discriminant);  // intersection la plus proche
vec3 hitPos = rayOrigin + t * rayDir;
vec3 N = normalize(hitPos - center);  // normale analytique parfaite
```

<pre class="mermaid">
graph TD
    R("🔦 Construction rayon — origin=camPos, dir=normalize(WorldPos-camPos)")
    R --> INT("📐 Intersection Rayon-Sphère — discriminant = b² - c")
    INT --> HIT{"Touché ?"}
    HIT -->|"Non — disc < 0"| DISCARD("❌ discard — pixel hors sphère")
    HIT -->|"Oui"| HITPOS("✅ hitPos = origin + t × dir")
    HITPOS --> NORMAL("N = normalize(hitPos - center) — normale parfaite")
    HITPOS --> DEPTH("gl_FragDepth = project(hitPos) — Z-buffer correct")
    NORMAL --> PBR("V = -rayDir")
    PBR --> FRESNEL("Fresnel-Schlick")
    PBR --> GGX("Smith-GGX Geometry")
    PBR --> NDF("GGX NDF Distribution")
    FRESNEL & GGX & NDF --> SPEC("IBL Spéculaire — prefilterMap × brdfLUT")
    PBR --> DIFF("IBL Diffuse — irradiance(N) × albedo")
    SPEC & DIFF --> FINAL("couleur = Diffuse + Spéculaire")
    FINAL --> AA("Anti-Aliasing bords — smoothstep sur discriminant")
    AA --> ALPHA("FragColor = vec4(color, edgeFactor) — alpha prémultiplié")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef compute fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef entryExit fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class R,INT,HIT keyFunc
    class HITPOS,NORMAL,DEPTH,PBR compute
    class FRESNEL,GGX,NDF,SPEC,DIFF subsystem
    class FINAL,AA,ALPHA,DISCARD entryExit
</pre>

#### Anti-aliasing analytique des bords

![Anti-aliasing analytique des sphères — smoothstep sur le discriminant]({static}/images/suckless-ogl/sphere_analytic_aa.webp)
*<center>L'anti-aliasing analytique utilise le discriminant comme métrique de distance au bord — pas besoin de [MSAA](#glossary-msaa "Multisample Anti-Aliasing — anti-crénelage géométrique (coûteux, évité ici)") pour des bords lisses.</center>*

```glsl
float pixelSizeWorld = (2.0 * clipW) / (proj[1][1] * screenHeight);
float edgeFactor = smoothstep(0.0, 1.0, discriminant / (2.0 * radius * pixelSizeWorld));
FragColor = vec4(color * edgeFactor, edgeFactor);  // alpha prémultiplié
```

![Détail de l'anti-aliasing parfait des sphères]({static}/images/suckless-ogl/sphere_perfect_aa_detail.webp)
*<center>Détail en gros plan : les bords des sphères sont parfaitement lisses grâce au [ray-tracing](#glossary-ray-tracing "Technique qui trace des rayons lumineux pour calculer l'intersection avec des objets") analytique.</center>*

#### Projection billboard

![Optimisation de projection AABB des sphères]({static}/images/suckless-ogl/sphere_aabb_optimization_projective.webp)
*<center>Le [vertex shader](#glossary-vertex-shader "Shader qui traite chaque sommet de la géométrie (position, projection)") calcule un quad serré à l'écran via projection tangentielle analytique, gérant 3 cas : caméra dehors, dedans, ou derrière la sphère.</center>*

---

## Chapitre 10 — Pipeline de post-processing

Après le rendu de la scène 3D dans le [FBO](#glossary-fbo "Framebuffer Object — surface de rendu offscreen (on dessine dedans au lieu de l'écran)") [MRT](#glossary-mrt "Multiple Render Targets — écrire dans plusieurs textures en une seule passe de rendu"), `postprocess_end()` applique jusqu'à **8 effets** dans un pipeline soigneusement ordonné.

### 10.1 — Le pipeline en 7 étapes

<pre class="mermaid">
graph TD
    A("Memory Barrier — flush écriture MRT")
    A --> B("① Bloom — Downsample → Seuil → Upsample")
    B --> C("② Profondeur de Champ — CoC → Flou bokeh")
    C --> D("③ Auto-Exposition — Réduction luminance → PBO readback")
    D --> E("④ Motion Blur — Tile-max velocity → Neighbor-max")
    E --> F("⑤ Bind 9 Textures + Upload UBO")
    F --> H("Draw fullscreen quad")
    H --> J("Vignette")
    J --> K("Grain film")
    K --> L("Balance des blancs")
    L --> M("Color Grading — Sat, Contraste, Gamma, Gain")
    M --> N("Tonemapping — courbe filmique")
    N --> O("Grading 3D LUT")
    O --> P("FXAA")
    P --> Q("Dithering — anti-banding")
    Q --> R("Brouillard atmosphérique")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef compute fill:#f3e5f5,stroke:#ab47bc,stroke-width:1.5px,color:#2d2d2d
    classDef shader fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class A,F,H subsystem
    class B,C,D,E compute
    class J,K,L,M,N,O,P,Q,R shader
</pre>

### 10.2 — Galerie des effets de post-processing

Voici le rendu **vue de face** avec différents effets activés individuellement — chaque image montre l'effet isolé appliqué à la même scène :

#### Sans post-processing (brut)
![Rendu brut sans aucun post-processing]({static}/images/suckless-ogl/ref_front_subtle_none.webp)
*<center>Image brute en sortie du rendu [PBR](#glossary-pbr "Physically-Based Rendering — modèle d'éclairage qui simule la physique réelle de la lumière") — pas de post-traitement appliqué.</center>*

#### FXAA (anti-aliasing rapide)
![Rendu avec FXAA activé]({static}/images/suckless-ogl/ref_front_subtle_fxaa.webp)
*<center>[FXAA](#glossary-fxaa "Fast Approximate Anti-Aliasing — anti-crénelage rapide en post-process sur l'image finale") (Fast Approximate Anti-Aliasing) — lisse les bords sans coût de [MSAA](#glossary-msaa "Multisample Anti-Aliasing — anti-crénelage géométrique (coûteux, évité ici)").</center>*

#### Bloom
![Rendu avec Bloom activé]({static}/images/suckless-ogl/ref_front_subtle_bloom.webp)
*<center>[Bloom](#glossary-bloom "Effet de halo lumineux autour des zones très brillantes (diffusion lumineuse de l'objectif)") — les zones lumineuses débordent, simulant la diffusion lumineuse d'un objectif.</center>*

#### Depth of Field (Profondeur de champ)
![Rendu avec Depth of Field activé]({static}/images/suckless-ogl/ref_front_subtle_dof.webp)
*<center>Profondeur de champ — les objets hors focus sont floutés comme avec un vrai objectif.</center>*

#### Auto-Exposure
![Rendu avec Auto-Exposure activé]({static}/images/suckless-ogl/ref_front_subtle_auto_exposure.webp)
*<center>[Auto-exposition](#glossary-auto-exposition "Adaptation automatique de la luminosité de la scène (simule l'iris de l'œil)") — le moteur adapte l'exposition comme l'œil humain s'adaptant à la luminosité.</center>*

#### Motion Blur
![Rendu avec Motion Blur activé]({static}/images/suckless-ogl/ref_front_subtle_motion_blur.webp)
*<center>[Motion blur](#glossary-motion-blur "Flou de mouvement par pixel simulant l'obturateur d'une caméra") par pixel — utilise les vecteurs de vélocité pour simuler le flou de mouvement cinématique.</center>*

#### Profil cinématique Sony A7S III
![Rendu avec profil Sony A7S III]({static}/images/suckless-ogl/ref_front_sony_a7siii.webp)
*<center>Profil photographique complet Sony A7S III — [color grading](#glossary-color-grading "Ajustement créatif des couleurs (saturation, contraste, gamma, teinte)"), balance, exposition et LUT 3D combinés pour un rendu cinématique.</center>*

### 10.3 — Optimisation shader par compilation conditionnelle

Le [fragment shader](#glossary-fragment-shader "Shader qui calcule la couleur de chaque pixel à l'écran") post-process utilise des **#define au compile-time** pour éliminer les branches :

```glsl
#ifdef OPT_ENABLE_BLOOM
    color += bloomTexture * bloomIntensity;
#endif

#ifdef OPT_ENABLE_FXAA
    color = fxaa(color, uv, texelSize);
#endif
```

Un **cache LRU de 32 entrées** stocke les variantes compilées pour différentes combinaisons de flags d'effets. Changer d'effet déclenche une recompilation paresseuse uniquement à la première occurrence d'une nouvelle combinaison.

### 10.4 — Courbes de tonemapping

![Courbes de tonemapping comparées]({static}/images/suckless-ogl/tonemapping_curves.webp)
*<center>Comparaison des courbes de [tonemapping](#glossary-tonemapping "Conversion des couleurs HDR (illimitées) en LDR affichable (0–255)") disponibles — le passage de [HDR](#glossary-hdr "High Dynamic Range — valeurs de couleur supérieures à 1.0 (lumière réaliste)") linéaire à LDR affichable.</center>*

### 10.5 — Adaptation d'exposition

![Adaptation d'exposition au fil du temps]({static}/images/suckless-ogl/exposure_adaptation.webp)
*<center>L'auto-exposition adapte progressivement la luminosité de la frame, comme l'iris de l'œil.</center>*

---

## Chapitre 11 — La première frame visible

Voyons ce qui apparaît réellement à l'écran pendant les premières secondes :

### Timeline de démarrage

| Frames | Ce qui se passe | À l'écran |
|--------|----------------|-----------|
| **1–2** | Le loader async lit `env.hdr` depuis le disque | Écran noir (`transition_alpha = 1.0`) |
| **3–4** | Transfert PBO → GPU (DMA) + génération mipmaps | Écran noir |
| **5–15** | Calcul [IBL](#glossary-ibl "Image-Based Lighting — éclairage extrait d'une image panoramique HDR de l'environnement") progressif ([luminance](#glossary-luminance "Mesure de l'intensité lumineuse perçue d'une image — utilisée pour l'auto-exposition"), spéculaire, [irradiance](#glossary-irradiance-map "Texture encodant la lumière ambiante diffuse intégrée sur l'hémisphère pour chaque direction")) | Écran noir (mais les sphères sont rendues dans le [FBO](#glossary-fbo "Framebuffer Object — surface de rendu offscreen (on dessine dedans au lieu de l'écran)")) |
| **~16** | IBL terminé → `TRANSITION_FADE_IN` | Le fade-in commence |
| **~20+** | Transition terminée — état stable | Scène PBR complètement éclairée |

### Frame en état stable

| Étape | Détail | Temps |
|-------|--------|-------|
| **1. Poll Events** | `glfwPollEvents()` | ~0.1ms CPU |
| **2. Mise à jour caméra** | Physique 60Hz + lerp rotation | ~0.01ms CPU |
| **3a. Skybox** | Quad plein écran, sampling equirect. | ~0.2ms GPU |
| **3b. Tri bitonique** | Compute shader, 100 sphères | ~0.1ms GPU |
| **3c. Sphères billboard** | 100 quads ray-tracées, 1 draw call | ~0.5ms GPU |
| **4a. Bloom** | Downsample → Upsample (si activé) | ~0.3ms GPU |
| **4b. DoF** | CoC → Flou bokeh (si activé) | ~0.2ms GPU |
| **4c. [Auto-Exposure](#glossary-auto-exposition "Adaptation automatique de la luminosité de la scène (simule l'iris de l'œil)")** | Réduction [luminance](#glossary-luminance "Mesure de l'intensité lumineuse perçue d'une image — utilisée pour l'auto-exposition") | ~0.1ms GPU |
| **4d. [Motion Blur](#glossary-motion-blur "Flou de mouvement par pixel simulant l'obturateur d'une caméra")** | [Tile-max velocity](#glossary-tile-max-velocity "Texture intermédiaire qui stocke la vélocité maximale par tuile (ex: 20×20 pixels), pour optimiser le motion blur") (si activé) | ~0.2ms GPU |
| **4e. Composite final** | 9 textures, UBO, fullscreen quad | ~0.3ms GPU |
| **5. UI Overlay** | Texte + profiler + transition | ~0.1ms GPU |
| **6. SwapBuffers** | Présentation à l'écran | (attente) |
| | **Temps de frame typique** | **1–3ms GPU** |

---

## Chapitre 12 — Budget mémoire GPU

Voici une estimation de la consommation [VRAM](#glossary-vram "Mémoire dédiée du GPU — c'est là que vivent textures et buffers") en état stable :

### Textures

| Ressource | Résolution | Format | Taille |
|-----------|-----------|--------|--------|
| HDR Environnement | 2048×1024 | `GL_RGBA16F` | ~16 Mo (avec mips) |
| Prefiltre Spéculaire | 1024² × 5 mips | `GL_RGBA16F` | ~10.5 Mo |
| Irradiance | 64×64 | `GL_RGBA16F` | ~32 Ko |
| BRDF LUT | 512×512 | `GL_RG16F` | ~1 Mo |
| Couleur Scène (FBO) | 1920×1080 | `GL_RGBA16F` | ~16 Mo |
| Vélocité (FBO) | 1920×1080 | `GL_RG16F` | ~8 Mo |
| Depth/Stencil (FBO) | 1920×1080 | `GL_DEPTH32F_STENCIL8` | ~10 Mo |
| Chaîne Bloom (6 mips) | Divers | `GL_RGBA16F` | ~21 Mo |
| DoF flou | 1920×1080 | `GL_RGBA16F` | ~16 Mo |
| Auto-Exposure | 64×64 → 1×1 | `GL_R32F` | ~16 Ko |
| SH Probes (7 tex) | 21×21×3 | `GL_RGBA16F` | ~74 Ko |

### Buffers

| Ressource | Quantité | Taille unitaire | Total |
|-----------|----------|----------------|-------|
| Billboard quad VBO | 4 verts | 12 o (vec3) | 48 o |
| Instance VBO | 100 instances | ~88 o | ~8.6 Ko |
| Sort SSBO | 100 entrées | 8 o | ~800 o |
| Fullscreen quad VBO | 6 verts | 20 o | 120 o |
| UBO (post-process) | 1 | ~256 o | 256 o |

### Total estimé

| Catégorie | Approximatif |
|----------|-------------|
| Textures | ~99 Mo |
| Buffers | ~40 Ko |
| Shaders (compilés) | ~2 Mo |
| **Total** | **~101 Mo VRAM** |

> **💡 Coût dominant** : La map [HDR](#glossary-hdr "High Dynamic Range — valeurs de couleur supérieures à 1.0 (lumière réaliste)") d'environnement + chaîne [bloom](#glossary-bloom "Effet de halo lumineux autour des zones très brillantes (diffusion lumineuse de l'objectif)") + FBOs de scène dominent l'utilisation VRAM. La géométrie elle-même (100 quads [billboard](#glossary-billboard "Quad (rectangle) toujours face à la caméra, utilisé ici comme surface de ray-tracing") × 4 vertices en mode par défaut) est négligeable — le vrai calcul de sphère se passe dans le [fragment shader](#glossary-fragment-shader "Shader qui calcule la couleur de chaque pixel à l'écran") via [ray-tracing](#glossary-ray-tracing "Technique qui trace des rayons lumineux pour calculer l'intersection avec des objets").

---

## Galerie : vues multi-angles

Le moteur supporte des captures automatisées depuis différents angles de caméra, utilisées pour les tests de régression visuelle :

<table style="width:100%; border-collapse:collapse; border:none;">
<tr>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_front.webp" alt="Vue de face" style="max-width:100%;"><br><em>Face</em></td>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_left.webp" alt="Vue de gauche" style="max-width:100%;"><br><em>Gauche</em></td>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_right.webp" alt="Vue de droite" style="max-width:100%;"><br><em>Droite</em></td>
</tr>
<tr>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_top.webp" alt="Vue du dessus" style="max-width:100%;"><br><em>Dessus</em></td>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_bottom.webp" alt="Vue du dessous" style="max-width:100%;"><br><em>Dessous</em></td>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_front_sony_a7siii.webp" alt="Profil Sony A7S III" style="max-width:100%;"><br><em>Sony A7S III</em></td>
</tr>
</table>

---

## Pipeline de données global

<pre class="mermaid">
graph TD
    POLL("① CPU — glfwPollEvents()") --> TIME("② CPU — Calcul Δt")
    TIME --> CAM("③ CPU — Physique caméra 60Hz")
    CAM --> SORT("④ CPU → GPU — Tri des sphères")
    SORT --> FBO("⑤ GPU — Bind Scene FBO, Clear")
    FBO --> SKY("🌅 Pass Skybox — Sampling equirectangulaire")
    SKY --> SPHERES("🔮 Pass Billboard — 1 draw call, 100 instances, ray-tracing")
    SPHERES --> BLOOM("✨ Bloom + DoF + Auto-Exposure + Motion Blur")
    BLOOM --> COMP("🎬 Composite Final — 9 textures, UBO, fullscreen quad")
    COMP --> UI("🖥️ UI Overlay + Profiler + Transition")
    UI --> SWAP("⑩ glfwSwapBuffers()")

    classDef cpu fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef gpu fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef postfx fill:#f3e5f5,stroke:#ab47bc,stroke-width:1.5px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class POLL,TIME,CAM,SORT cpu
    class FBO,SKY,SPHERES gpu
    class BLOOM,COMP postfx
    class UI,SWAP subsystem
</pre>

---

## Glossaire

> Référence rapide des termes techniques utilisés dans l'article, avec liens vers la documentation officielle.

### Langages, API & Standards

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-c11"></a>**C11** | Version 2011 du standard du langage C, utilisé pour tout le moteur | [cppreference — C11](https://en.cppreference.com/w/c/11) |
| <a id="glossary-opengl-44"></a>**OpenGL 4.4** | API graphique bas-niveau pour communiquer avec le GPU | [OpenGL 4.4 Spec (Khronos)](https://registry.khronos.org/OpenGL/specs/gl/glspec44.core.pdf) |
| <a id="glossary-core-profile"></a>**Core Profile** | Mode OpenGL qui retire les fonctions dépréciées (pipeline fixe) | [OpenGL Wiki — Core Profile](https://www.khronos.org/opengl/wiki/OpenGL_Context#OpenGL_3.1_and_ARB_compatibility) |
| <a id="glossary-glsl"></a>**GLSL** | *OpenGL Shading Language* — langage des programmes GPU (shaders) | [GLSL Spec (Khronos)](https://registry.khronos.org/OpenGL/specs/gl/GLSLangSpec.4.40.pdf) |
| <a id="glossary-glfw"></a>**GLFW** | Bibliothèque C pour créer des fenêtres et gérer les entrées clavier/souris | [glfw.org](https://www.glfw.org/documentation.html) |
| <a id="glossary-window-hints"></a>**Window Hints** | Paramètres GLFW configurés avant la création de la fenêtre (version OpenGL, profil, MSAA…) | [GLFW — Window Guide](https://www.glfw.org/docs/latest/window_guide.html#window_hints) |
| <a id="glossary-glad"></a>**GLAD** | Générateur de loader OpenGL — résout les adresses des fonctions GL au runtime | [GLAD Generator](https://glad.dav1d.de/) |
| <a id="glossary-glx"></a>**GLX** | Extension X11 qui fait le pont entre le Window System et OpenGL sous Linux | [GLX Spec (Khronos)](https://registry.khronos.org/OpenGL/specs/gl/glx1.4.pdf) |
| <a id="glossary-x11"></a>**X11** | Système de fenêtrage historique de Linux (serveur d'affichage) | [X.Org](https://www.x.org/wiki/) |
| <a id="glossary-mesa"></a>**Mesa** | Implémentation open-source des API graphiques (OpenGL, Vulkan) sous Linux | [mesa3d.org](https://www.mesa3d.org/) |

### Rendu 3D — Concepts fondamentaux

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-pbr"></a>**PBR** | *Physically-Based Rendering* — modèle d'éclairage qui simule la physique réelle de la lumière | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-ibl"></a>**IBL** | *Image-Based Lighting* — éclairage extrait d'une image panoramique HDR de l'environnement | [learnopengl.com — IBL](https://learnopengl.com/PBR/IBL/Diffuse-irradiance) |
| <a id="glossary-hdr"></a>**HDR** | *High Dynamic Range* — valeurs de couleur supérieures à 1.0 (lumière réaliste) | [learnopengl.com — HDR](https://learnopengl.com/Advanced-Lighting/HDR) |
| <a id="glossary-ldr"></a>**LDR** | *Low Dynamic Range* — valeurs de couleur 0–255, ce que l'écran affiche réellement | [learnopengl.com — HDR](https://learnopengl.com/Advanced-Lighting/HDR) |
| <a id="glossary-shader"></a>**Shader** | Programme exécuté directement sur le GPU (vertex, fragment, compute) | [OpenGL Wiki — Shader](https://www.khronos.org/opengl/wiki/Shader) |
| <a id="glossary-vertex-shader"></a>**Vertex Shader** | Shader qui traite chaque sommet de la géométrie (position, projection) | [OpenGL Wiki — Vertex Shader](https://www.khronos.org/opengl/wiki/Vertex_Shader) |
| <a id="glossary-fragment-shader"></a>**Fragment Shader** | Shader qui calcule la couleur de chaque pixel à l'écran | [OpenGL Wiki — Fragment Shader](https://www.khronos.org/opengl/wiki/Fragment_Shader) |
| <a id="glossary-compute-shader"></a>**Compute Shader** | Shader généraliste pour du calcul GPU hors pipeline de rendu | [OpenGL Wiki — Compute Shader](https://www.khronos.org/opengl/wiki/Compute_Shader) |
| <a id="glossary-skybox"></a>**Skybox** | Image panoramique affichée en fond de scène comme ciel/environnement | [learnopengl.com — Cubemaps](https://learnopengl.com/Advanced-OpenGL/Cubemaps) |
| <a id="glossary-rasterisation"></a>**Rasterisation** | Processus de conversion des triangles 3D en pixels 2D à l'écran | [OpenGL Wiki — Rasterization](https://www.khronos.org/opengl/wiki/Rasterization) |
| <a id="glossary-draw-call"></a>**Draw Call** | Un appel CPU→GPU qui demande le rendu d'un jeu de géométrie | [OpenGL Wiki — Rendering Pipeline](https://www.khronos.org/opengl/wiki/Rendering_Pipeline_Overview) |
| <a id="glossary-instanced-rendering"></a>**Instanced Rendering** | Technique pour dessiner N copies d'un objet en un seul draw call | [OpenGL Wiki — Instancing](https://www.khronos.org/opengl/wiki/Vertex_Rendering#Instancing) |
| <a id="glossary-mipmap"></a>**Mipmap** | Versions pré-réduites d'une texture (½, ¼, ⅛…) pour un filtrage plus propre au loin | [OpenGL Wiki — Texture#Mip_maps](https://www.khronos.org/opengl/wiki/Texture#Mip_maps) |

### Objets GPU OpenGL

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-fbo"></a>**FBO** | *Framebuffer Object* — surface de rendu offscreen (on dessine dedans au lieu de l'écran) | [OpenGL Wiki — Framebuffer Object](https://www.khronos.org/opengl/wiki/Framebuffer_Object) |
| <a id="glossary-mrt"></a>**MRT** | *Multiple Render Targets* — écrire dans plusieurs textures en une seule passe de rendu | [OpenGL Wiki — MRT](https://www.khronos.org/opengl/wiki/Framebuffer_Object#Multiple_Render_Targets) |
| <a id="glossary-vao"></a>**VAO** | *Vertex Array Object* — décrit le format des données géométriques envoyées au GPU | [OpenGL Wiki — VAO](https://www.khronos.org/opengl/wiki/Vertex_Specification#Vertex_Array_Object) |
| <a id="glossary-vbo"></a>**VBO** | *Vertex Buffer Object* — buffer GPU contenant les positions, normales, etc. des sommets | [OpenGL Wiki — VBO](https://www.khronos.org/opengl/wiki/Vertex_Specification#Vertex_Buffer_Object) |
| <a id="glossary-ssbo"></a>**SSBO** | *Shader Storage Buffer Object* — buffer GPU en lecture/écriture depuis les shaders | [OpenGL Wiki — SSBO](https://www.khronos.org/opengl/wiki/Shader_Storage_Buffer_Object) |
| <a id="glossary-ubo"></a>**UBO** | *Uniform Buffer Object* — bloc de données partagé entre CPU et shaders | [OpenGL Wiki — UBO](https://www.khronos.org/opengl/wiki/Uniform_Buffer_Object) |
| <a id="glossary-pbo"></a>**PBO** | *Pixel Buffer Object* — buffer pour les transferts asynchrones de pixels CPU↔GPU | [OpenGL Wiki — PBO](https://www.khronos.org/opengl/wiki/Pixel_Buffer_Object) |
| <a id="glossary-texture-view"></a>**Texture View** | Vue alternative sur les données d'une texture existante (format ou couches différents) | [OpenGL Wiki — Texture View](https://www.khronos.org/opengl/wiki/Texture_Storage#Texture_views) |

### Ray-Tracing & Géométrie

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-ray-tracing"></a>**Ray-Tracing** | Technique qui trace des rayons lumineux pour calculer l'intersection avec des objets | [Scratchapixel — Ray-Sphere](https://www.scratchapixel.com/lessons/3d-basic-rendering/minimal-ray-tracer-rendering-simple-shapes/ray-sphere-intersection.html) |
| <a id="glossary-billboard"></a>**Billboard** | Quad (rectangle) toujours face à la caméra, utilisé ici comme surface de ray-tracing | [OpenGL Wiki — Billboard](https://www.khronos.org/opengl/wiki/Billboards) |
| <a id="glossary-aabb"></a>**AABB** | *Axis-Aligned Bounding Box* — boîte englobante alignée aux axes, pour le culling rapide | [Wikipedia — AABB](https://en.wikipedia.org/wiki/Minimum_bounding_box#Axis-aligned_minimum_bounding_box) |
| <a id="glossary-icosphre"></a>**Icosphère** | Sphère construite en subdivisant un icosaèdre (20 faces) — plus uniforme qu'une UV sphere | [Wikipedia — Icosphère](https://en.wikipedia.org/wiki/Geodesic_polyhedron) |
| <a id="glossary-discriminant"></a>**Discriminant** | Valeur mathématique (b²−c) déterminant si un rayon touche une sphère | [Scratchapixel — Ray-Sphere](https://www.scratchapixel.com/lessons/3d-basic-rendering/minimal-ray-tracer-rendering-simple-shapes/ray-sphere-intersection.html) |
| <a id="glossary-normale"></a>**Normale** | Vecteur perpendiculaire à la surface en un point — détermine l'orientation de la surface | [learnopengl.com — Basic Lighting](https://learnopengl.com/Lighting/Basic-Lighting) |
| <a id="glossary-tessellation"></a>**Tessellation** | Subdivision de la géométrie en triangles plus fins pour plus de détail | [OpenGL Wiki — Tessellation](https://www.khronos.org/opengl/wiki/Tessellation) |
| <a id="glossary-mesh"></a>**Mesh** | Ensemble de triangles formant un objet 3D | [Wikipedia — Polygon mesh](https://en.wikipedia.org/wiki/Polygon_mesh) |
| <a id="glossary-quad"></a>**Quad** | Rectangle composé de 2 triangles — la primitive 2D de base | [learnopengl.com — Hello Triangle](https://learnopengl.com/Getting-started/Hello-Triangle) |
| <a id="glossary-anti-aliasing"></a>**Anti-aliasing** | Technique de lissage des bords en escalier (aliasing) pour un rendu visuellement plus propre | [Wikipedia — Anti-aliasing](https://en.wikipedia.org/wiki/Spatial_anti-aliasing) |

### PBR & Éclairage

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-brdf"></a>**BRDF** | *Bidirectional Reflectance Distribution Function* — fonction décrivant comment la lumière rebondit sur une surface | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-brdf-lut"></a>**BRDF LUT** | Texture pré-calculée qui encode l'intégrale BRDF pour toutes les combinaisons (angle, rugosité) | [learnopengl.com — Specular IBL](https://learnopengl.com/PBR/IBL/Specular-IBL) |
| <a id="glossary-fresnel-schlick"></a>**Fresnel-Schlick** | Approximation de l'effet Fresnel : les surfaces reflètent plus en angle rasant | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-ggx---smith-ggx"></a>**GGX / Smith-GGX** | Modèle de micro-facettes pour la géométrie et distribution des normales (rugosité) | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-ndf"></a>**NDF** | *Normal Distribution Function* — distribution statistique de l'orientation des micro-facettes | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-albedo"></a>**Albedo** | Couleur de base d'un matériau (sans éclairage) | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-metallic"></a>**Metallic** | Paramètre PBR : 0 = diélectrique (plastique, bois), 1 = métal (or, chrome) | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-roughness"></a>**Roughness** | Paramètre PBR : 0 = miroir parfait, 1 = complètement mat | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-ao"></a>**AO** | *Ambient Occlusion* — assombrit les creux et recoins (occlusion de la lumière ambiante) | [learnopengl.com — SSAO](https://learnopengl.com/Advanced-Lighting/SSAO) |
| <a id="glossary-dilectrique"></a>**Diélectrique** | Matériau non-métallique (plastique, verre, bois) — reflète peu à angle direct | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-irradiance-map"></a>**Irradiance Map** | Texture encodant la lumière ambiante diffuse intégrée sur l'hémisphère pour chaque direction | [learnopengl.com — Diffuse Irradiance](https://learnopengl.com/PBR/IBL/Diffuse-irradiance) |
| <a id="glossary-prefiltre-spculaire"></a>**Prefiltre Spéculaire** | Texture mip-mappée encodant les réflexions floues par niveau de rugosité | [learnopengl.com — Specular IBL](https://learnopengl.com/PBR/IBL/Specular-IBL) |
| <a id="glossary-equirectangulaire"></a>**Equirectangulaire** | Projection 2D d'une sphère (comme une carte du monde) — le format des images HDR `.hdr` | [Wikipedia — Equirectangular](https://en.wikipedia.org/wiki/Equirectangular_projection) |
| <a id="glossary-sh-probes"></a>**SH Probes** | *Spherical Harmonics* — représentation compacte d'un champ lumineux basse fréquence | [Wikipedia — SH Lighting](https://en.wikipedia.org/wiki/Spherical_harmonic_lighting) |

### Post-Processing

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-bloom"></a>**Bloom** | Effet de halo lumineux autour des zones très brillantes (diffusion lumineuse de l'objectif) | [learnopengl.com — Bloom](https://learnopengl.com/Advanced-Lighting/Bloom) |
| <a id="glossary-prefilter"></a>**Prefilter (Bloom)** | Passe initiale du bloom qui extrait les pixels au-dessus d'un seuil de luminosité | [learnopengl.com — Bloom](https://learnopengl.com/Advanced-Lighting/Bloom) |
| <a id="glossary-downsample"></a>**Downsample** | Réduction progressive de la résolution d'une texture (par 2 à chaque niveau) | [learnopengl.com — Bloom](https://learnopengl.com/Advanced-Lighting/Bloom) |
| <a id="glossary-upsample"></a>**Upsample** | Agrandissement progressif d'une texture basse résolution vers la résolution originale | [learnopengl.com — Bloom](https://learnopengl.com/Advanced-Lighting/Bloom) |
| <a id="glossary-depth-of-field-dof"></a>**Depth of Field (DoF)** | Profondeur de champ — flou des objets hors de la distance de mise au point | [Wikipedia — Depth of field](https://en.wikipedia.org/wiki/Depth_of_field) |
| <a id="glossary-coc"></a>**CoC** | *Circle of Confusion* — diamètre du disque de flou d'un point hors focus | [Wikipedia — CoC](https://en.wikipedia.org/wiki/Circle_of_confusion) |
| <a id="glossary-bokeh"></a>**Bokeh** | Forme esthétique du flou d'arrière-plan (disques, hexagones…) | [Wikipedia — Bokeh](https://en.wikipedia.org/wiki/Bokeh) |
| <a id="glossary-motion-blur"></a>**Motion Blur** | Flou de mouvement par pixel simulant l'obturateur d'une caméra | [GPU Gems — Motion Blur](https://developer.nvidia.com/gpugems/gpugems3/part-iv-image-effects/chapter-27-motion-blur-post-processing-effect) |
| <a id="glossary-tile-max-velocity"></a>**Tile-Max Velocity** | Texture intermédiaire qui stocke la vélocité maximale par tuile (ex: 20×20 pixels), pour optimiser le motion blur | [McGuire — Motion Blur](https://casual-effects.com/research/McGuire2012Blur/index.html) |
| <a id="glossary-neighbor-max"></a>**Neighbor-Max** | Texture qui propage la vélocité max aux tuiles voisines, couvrant le flou de mouvement inter-tuiles | [McGuire — Motion Blur](https://casual-effects.com/research/McGuire2012Blur/index.html) |
| <a id="glossary-cube-format"></a>**.cube** | Format de fichier texte définissant une LUT 3D de correspondance couleur, standard dans le cinéma et les DCC | [Adobe — .cube LUT Spec](https://wwwimages2.adobe.com/content/dam/acom/en/products/speedgrade/cc/pdfs/cube-lut-specification-1.0.pdf) |
| <a id="glossary-fxaa"></a>**FXAA** | *Fast Approximate Anti-Aliasing* — anti-crénelage rapide en post-process sur l'image finale | [NVIDIA — FXAA](https://developer.download.nvidia.com/assets/gamedev/files/sdk/11/FXAA_WhitePaper.pdf) |
| <a id="glossary-msaa"></a>**MSAA** | *Multisample Anti-Aliasing* — anti-crénelage géométrique (coûteux, évité ici) | [OpenGL Wiki — Multisampling](https://www.khronos.org/opengl/wiki/Multisampling) |
| <a id="glossary-tonemapping"></a>**Tonemapping** | Conversion des couleurs HDR (illimitées) en LDR affichable (0–255) | [learnopengl.com — HDR](https://learnopengl.com/Advanced-Lighting/HDR) |
| <a id="glossary-color-grading"></a>**Color Grading** | Ajustement créatif des couleurs (saturation, contraste, gamma, teinte) | [Wikipedia — Color grading](https://en.wikipedia.org/wiki/Color_grading) |
| <a id="glossary-3d-lut"></a>**3D LUT** | Table 3D de correspondance couleur → couleur pour un "look" cinématique (fichier `.cube`) | [Wikipedia — 3D LUT](https://en.wikipedia.org/wiki/3D_lookup_table) |
| <a id="glossary-vignette"></a>**Vignette** | Assombrissement progressif des bords de l'image (effet objectif) | [Wikipedia — Vignetting](https://en.wikipedia.org/wiki/Vignetting) |
| <a id="glossary-grain-film"></a>**Grain film** | Bruit photographique simulé ajouté à l'image pour un rendu analogique/cinématique | [Wikipedia — Film grain](https://en.wikipedia.org/wiki/Film_grain) |
| <a id="glossary-balance-des-blancs"></a>**Balance des blancs** | Correction de la température de couleur pour que les blancs apparaissent neutres sous différents éclairages | [Wikipedia — White balance](https://en.wikipedia.org/wiki/Color_balance) |
| <a id="glossary-brouillard-atmospherique"></a>**Brouillard atmosphérique** | Effet de profondeur qui estompe et teinte les objets lointains, simulant la diffusion de la lumière dans l'air | [Wikipedia — Atmospheric scattering](https://en.wikipedia.org/wiki/Rayleigh_scattering) |
| <a id="glossary-dithering"></a>**Dithering** | Ajout de bruit imperceptible pour casser les artefacts de banding dans les dégradés | [Wikipedia — Dither](https://en.wikipedia.org/wiki/Dither) |
| <a id="glossary-auto-exposition"></a>**Auto-Exposition** | Adaptation automatique de la luminosité de la scène (simule l'iris de l'œil) | [learnopengl.com — HDR](https://learnopengl.com/Advanced-Lighting/HDR) |
| <a id="glossary-luminance"></a>**Luminance** | Mesure de l'intensité lumineuse perçue d'une image — utilisée pour l'auto-exposition | [Wikipedia — Luminance](https://en.wikipedia.org/wiki/Relative_luminance) |
| <a id="glossary-luma"></a>**Luma** | Approximation rapide de la luminance perçue (0.299R + 0.587G + 0.114B) — utilisée par FXAA pour détecter les bords | [Wikipedia — Luma](https://en.wikipedia.org/wiki/Luma_(video)) |
| <a id="glossary-vsync"></a>**VSync** | *Vertical Sync* — synchronise le rendu avec le rafraîchissement de l'écran (évite le tearing) | [Wikipedia — VSync](https://en.wikipedia.org/wiki/Screen_tearing#V-sync) |

### Architecture & Performance

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-simd"></a>**SIMD** | *Single Instruction, Multiple Data* — calcul vectoriel (1 instruction traite 4+ valeurs) | [Wikipedia — SIMD](https://en.wikipedia.org/wiki/Single_instruction,_multiple_data) |
| <a id="glossary-sse"></a>**SSE** | Extensions SIMD d'Intel/AMD pour le x86 (registres 128-bit) | [Intel — SSE Intrinsics](https://www.intel.com/content/www/us/en/docs/intrinsics-guide/index.html) |
| <a id="glossary-neon"></a>**NEON** | Extensions SIMD d'ARM (smartphones, Apple Silicon, Raspberry Pi) | [ARM — NEON](https://developer.arm.com/Architectures/Neon) |
| <a id="glossary-vram"></a>**VRAM** | Mémoire dédiée du GPU — c'est là que vivent textures et buffers | [Wikipedia — VRAM](https://en.wikipedia.org/wiki/Video_RAM_(dual-ported_DRAM)) |
| <a id="glossary-dma"></a>**DMA** | *Direct Memory Access* — transfert de données sans impliquer le CPU | [Wikipedia — DMA](https://en.wikipedia.org/wiki/Direct_memory_access) |
| <a id="glossary-cache-friendly"></a>**Cache-friendly** | Organisation mémoire qui minimise les cache-miss CPU (données contiguës) | [Wikipedia — Cache](https://en.wikipedia.org/wiki/CPU_cache#Cache-friendly_code) |
| <a id="glossary-lru-cache"></a>**LRU Cache** | *Least Recently Used* — cache qui éjecte l'élément le moins récemment utilisé | [Wikipedia — LRU](https://en.wikipedia.org/wiki/Cache_replacement_policies#Least_recently_used_(LRU)) |
| <a id="glossary-fence-glsync"></a>**Fence (GLSync)** | Objet de synchronisation GPU — permet d'attendre qu'un travail GPU soit terminé | [OpenGL Wiki — Sync Object](https://www.khronos.org/opengl/wiki/Sync_Object) |
| <a id="glossary-memory-barrier"></a>**Memory Barrier** | Instruction GPU garantissant que les écritures précédentes sont visibles avant les lectures suivantes | [OpenGL Wiki — Memory Barrier](https://www.khronos.org/opengl/wiki/Memory_Model#Explicit_memory_barriers) |
| <a id="glossary-work-group"></a>**Work Group** | Groupe de threads GPU exécutés ensemble dans un compute shader (ex: 16×16 = 256 threads) | [OpenGL Wiki — Compute Shader](https://www.khronos.org/opengl/wiki/Compute_Shader#Compute_space) |
| <a id="glossary-dispatch"></a>**Dispatch** | Appel CPU qui lance un compute shader sur le GPU | [OpenGL Wiki — Compute Shader](https://www.khronos.org/opengl/wiki/Compute_Shader#Dispatch) |
| <a id="glossary-gpu-stall"></a>**GPU Stall** | Blocage du pipeline GPU quand il attend une ressource ou une synchronisation — provoque des chutes de framerate | [NVIDIA — GPU Performance](https://developer.nvidia.com/blog/the-peak-performance-analysis-method-for-optimizing-any-gpu-workload/) |
| <a id="glossary-llvmpipe"></a>**llvmpipe** | Driver OpenGL logiciel de Mesa — émule le GPU entièrement sur CPU via LLVM JIT, utilisé en CI ou sans carte graphique | [Mesa — llvmpipe](https://docs.mesa3d.org/drivers/llvmpipe.html) |

### Mathématiques & Caméra

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-mat4---vec3"></a>**mat4 / vec3** | Matrice 4×4 et vecteur 3D — types fondamentaux de la 3D | [cglm docs](https://cglm.readthedocs.io/en/latest/) |
| <a id="glossary-fov"></a>**FOV** | *Field of View* — angle de vision de la caméra (60° ici) | [Wikipedia — FOV](https://en.wikipedia.org/wiki/Field_of_view) |
| <a id="glossary-matrice-de-vue"></a>**Matrice de vue** | Transforme les coordonnées monde en coordonnées caméra (`lookAt`) | [learnopengl.com — Camera](https://learnopengl.com/Getting-started/Camera) |
| <a id="glossary-matrice-de-projection"></a>**Matrice de projection** | Transforme la 3D en 2D avec perspective (objets lointains = petits) | [learnopengl.com — Coordinate Systems](https://learnopengl.com/Getting-started/Coordinate-Systems) |
| <a id="glossary-yaw---pitch"></a>**Yaw / Pitch** | Yaw = rotation gauche-droite, Pitch = rotation haut-bas de la caméra | [learnopengl.com — Camera](https://learnopengl.com/Getting-started/Camera) |
| <a id="glossary-camera-orbitale"></a>**Caméra orbitale** | Contrôle caméra qui tourne autour d'un point d'intérêt via yaw/pitch depuis les mouvements souris | [learnopengl.com — Camera](https://learnopengl.com/Getting-started/Camera) |
| <a id="glossary-lerp"></a>**Lerp** | *Linear Interpolation* — transition progressive entre deux valeurs : `a + t × (b − a)` | [Wikipedia — Lerp](https://en.wikipedia.org/wiki/Linear_interpolation) |
| <a id="glossary-ema"></a>**EMA** | *Exponential Moving Average* — moyenne glissante qui donne plus de poids aux valeurs récentes | [Wikipedia — EMA](https://en.wikipedia.org/wiki/Exponential_smoothing) |
| <a id="glossary-smoothstep"></a>**Smoothstep** | Fonction d'interpolation en S (transition douce entre 0 et 1) | [Khronos — smoothstep](https://registry.khronos.org/OpenGL-Refpages/gl4/html/smoothstep.xhtml) |
| <a id="glossary-z-buffer---depth-buffer"></a>**Z-buffer / Depth Buffer** | Texture qui stocke la profondeur de chaque pixel pour gérer l'occlusion | [learnopengl.com — Depth Testing](https://learnopengl.com/Advanced-OpenGL/Depth-testing) |
| <a id="glossary-z-clip"></a>**Z-clip (Near/Far)** | Plans de découpage proche et lointain de la caméra — définissent la plage de profondeur visible | [learnopengl.com — Coordinate Systems](https://learnopengl.com/Getting-started/Coordinate-Systems) |
| <a id="glossary-stencil-buffer"></a>**Stencil Buffer** | Masque par pixel permettant de restreindre le rendu à certaines zones | [learnopengl.com — Stencil](https://learnopengl.com/Advanced-OpenGL/Stencil-testing) |

### Algorithmes de tri

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-bitonic-sort"></a>**Bitonic Sort** | Tri parallèle adapté au GPU — compare et échange par paires | [Wikipedia — Bitonic sort](https://en.wikipedia.org/wiki/Bitonic_sorter) |
| <a id="glossary-radix-sort"></a>**Radix Sort** | Tri par chiffres successifs — O(n·k), efficace sur CPU pour des clés entières | [Wikipedia — Radix sort](https://en.wikipedia.org/wiki/Radix_sort) |
| <a id="glossary-back-to-front"></a>**Back-to-front** | Ordre de rendu du plus loin au plus proche, nécessaire pour la transparence correcte | [Wikipedia — Painter's algorithm](https://en.wikipedia.org/wiki/Painter%27s_algorithm) |

### Multithreading

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-posix-threads"></a>**POSIX Threads** | API standard de threads sur Unix/Linux (`pthread_create`, `pthread_cond_wait`) | [man — pthreads](https://man7.org/linux/man-pages/man7/pthreads.7.html) |
| <a id="glossary-chargement-asynchrone"></a>**Chargement asynchrone** | Exécuter les I/O disque sur un thread séparé pour ne pas bloquer le rendu | [Wikipedia — Async I/O](https://en.wikipedia.org/wiki/Asynchronous_I/O) |
| <a id="glossary-variable-de-condition"></a>**Variable de condition** | Mécanisme de synchronisation : un thread dort jusqu'à ce qu'un autre le réveille | [man — pthread_cond_wait](https://man7.org/linux/man-pages/man3/pthread_cond_wait.3p.html) |

### Divers

| Terme | Description | Lien |
|-------|------------|------|
| <a id="glossary-tracy"></a>**Tracy** | Profiler temps réel pour jeux et applis graphiques (mesure CPU + GPU par frame) | [Tracy Profiler (GitHub)](https://github.com/wolfpld/tracy) |
| <a id="glossary-cglm"></a>**cglm** | Bibliothèque C de maths 3D optimisée SIMD (matrices, vecteurs, quaternions) | [cglm (GitHub)](https://github.com/recp/cglm) |
| <a id="glossary-stbimage"></a>**stb_image** | Bibliothèque C mono-fichier pour charger des images (PNG, JPEG, HDR…) | [stb (GitHub)](https://github.com/nothings/stb) |
| <a id="glossary-pas-fixe-fixed-timestep"></a>**Pas fixe (Fixed Timestep)** | Mise à jour de la physique à intervalle constant (ex: 60 Hz) indépendamment du framerate | [Fix Your Timestep! (Fiedler)](https://gafferongames.com/post/fix_your_timestep/) |
| <a id="glossary-game-loop"></a>**Game Loop** | Boucle principale d'un jeu : lire les entrées → mettre à jour → dessiner → recommencer | [Game Programming Patterns — Game Loop](https://gameprogrammingpatterns.com/game-loop.html) |
| <a id="glossary-frame-time"></a>**Frame Time** | Durée totale de rendu d'une image — 16.6ms à 60 FPS, tout dépassement provoque une saccade | [Wikipedia — Frame rate](https://en.wikipedia.org/wiki/Frame_rate) |
| <a id="glossary-fireflies"></a>**Fireflies** | Pixels aberrants ultra-lumineux causés par des valeurs HDR extrêmes (artefact) | [Physically Based — Fireflies](https://pbr-book.org/4ed/Sampling_and_Reconstruction/Filtering_Image_Samples#FireflyPrevention) |
| <a id="glossary-alpha-prmultipli"></a>**Alpha prémultiplié** | Convention où RGB est déjà multiplié par alpha — permet un blending correct | [Wikipedia — Premultiplied alpha](https://en.wikipedia.org/wiki/Alpha_compositing#Straight_versus_premultiplied) |
| <a id="glossary-face-culling"></a>**Face Culling** | Optimisation GPU qui élimine les triangles dont la face arrière est visible — désactivé ici pour les billboards | [OpenGL Wiki — Face Culling](https://www.khronos.org/opengl/wiki/Face_Culling) |
| <a id="glossary-include-guard"></a>**Include Guard** | Mécanisme de déduplication qui empêche un fichier d'être inclus plusieurs fois | [Wikipedia — Include guard](https://en.wikipedia.org/wiki/Include_guard) |
| <a id="glossary-zero-init"></a>**Zero-init** | Initialisation à zéro d'une structure C via `{0}` — garantit un état déterministe au démarrage | [cppreference — Zero initialization](https://en.cppreference.com/w/c/language/struct_initialization) |
| <a id="glossary-json"></a>**JSON** | *JavaScript Object Notation* — format de fichier texte léger pour stocker des données structurées (clé/valeur) | [json.org](https://www.json.org/json-fr.html) |

---

## Conclusion

**suckless-ogl** démontre qu'un moteur PBR complet peut être construit avec un code C11 lisible, un pipeline de rendu clair et des performances GPU mesurées en millisecondes. Les choix de design — billboard ray-tracing au lieu de mesh, chargement HDR asynchrone, IBL progressive, post-processing modulaire — montrent comment résoudre des problèmes graphiques réels avec élégance.

Le code source complet est disponible sur [GitHub](https://github.com/yoyonel/suckless-ogl), et la documentation technique détaillée sur [yoyonel.github.io/suckless-ogl](https://yoyonel.github.io/suckless-ogl/).

*Dans les prochains articles, on explorera les projets Vulkan et NVRHI qui poussent ces concepts encore plus loin.*
