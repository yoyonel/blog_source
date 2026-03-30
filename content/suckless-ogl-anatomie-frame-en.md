---
title: Anatomy of a Frame — The Complete Lifecycle of suckless-ogl
slug: suckless-ogl-anatomie-frame
lang: en
date: 2026-03-29
description: An illustrated technical deep-dive into the suckless-ogl PBR rendering engine — from main() to photons on screen. We trace every pipeline step: OpenGL initialization, async HDR loading, billboard ray-traced spheres, progressive IBL, and cinematic post-processing.
tags: OpenGL, C, PBR, IBL, 3D Rendering, GLSL, Ray-Tracing, Post-Processing, Development
category: Development
CSS: mermaid-dark.css, glossary-tooltip.css
JS: mermaid-init.js (top), glossary-tooltip.js
---

# Anatomy of a Frame: The Complete Lifecycle of suckless-ogl

*From `main()` to photons on screen — a full deep-dive into a modern OpenGL [PBR](#glossary-pbr "Physically-Based Rendering — lighting model that simulates real physics of light") engine written in C.*

![The final render of suckless-ogl — 100 PBR spheres lit by IBL]({static}/images/suckless-ogl/reference_image.png)
*<center>The final render: 100 [metallic](#glossary-metallic "PBR parameter: 0 = dielectric (plastic, wood), 1 = metal (gold, chrome)") and [dielectric](#glossary-dielectric "Non-metallic material (plastic, glass, wood) — reflects little at direct angles") spheres, lit by an [HDR](#glossary-hdr "High Dynamic Range — color values exceeding 1.0 (realistic light intensities)") environment map, with full post-processing.</center>*

---

## Introduction

[**suckless-ogl**](https://github.com/yoyonel/suckless-ogl) is a minimalist, high-performance [PBR](#glossary-pbr "Physically-Based Rendering — lighting model that simulates real physics of light") (Physically-Based Rendering) engine written in **C11** with **OpenGL 4.4 Core Profile**. It displays a grid of **100 spheres** with varied materials (metals, dielectrics, paints, organics…) lit by **Image-Based Lighting** ([IBL](#glossary-ibl "Image-Based Lighting — lighting extracted from a panoramic HDR environment image")), with a full post-processing pipeline: [bloom](#glossary-bloom "Glow halo around very bright areas (lens light diffusion)"), depth of field, [motion blur](#glossary-motion-blur "Per-pixel motion blur simulating a camera shutter"), [FXAA](#glossary-fxaa "Fast Approximate Anti-Aliasing — fast post-process anti-aliasing on the final image"), tone mapping, [color grading](#glossary-color-grading "Creative color adjustments (saturation, contrast, gamma, hue)")…

This article traces the **complete lifecycle** of the application: from the first byte allocated in `main()` to the moment the GPU presents the first fully-lit frame on screen. We'll walk through **every layer** — CPU memory, GPU resources, the X11/GLFW windowing handshake, OpenGL context creation, [shader](#glossary-shader "Program executed directly on the GPU (vertex, fragment, compute)") compilation, async texture loading, and the multi-pass rendering architecture that produces each frame.

### What We'll Cover

| Chapter | Topic |
|---------|-------|
| [1](#chapter-1-the-entry-point) | The entry point (`main()`) |
| [2](#chapter-2-opening-a-window-glfw-x11-opengl) | Opening a window (GLFW + X11 + OpenGL) |
| [3](#chapter-3-cpu-side-initialization) | CPU-side initialization (camera, threads, buffers) |
| [4](#chapter-4-scene-initialization-the-gpu-wakes-up) | Scene initialization (GPU) |
| [5](#chapter-5-post-processing-pipeline-setup) | Post-processing pipeline |
| [6](#chapter-6-the-first-hdr-environment-load) | Async HDR environment loading |
| [7](#chapter-7-ibl-generation-progressive-multi-frame) | Progressive IBL generation |
| [8](#chapter-8-the-main-loop) | The main loop |
| [9](#chapter-9-rendering-a-frame) | Rendering a frame |
| [10](#chapter-10-post-processing-pipeline) | Post-processing in detail |
| [11](#chapter-11-the-first-visible-frame) | The first visible frame |
| [12](#chapter-12-gpu-memory-budget) | GPU memory budget |

---

## Chapter 1 — The Entry Point

Everything begins in `main()` ([src/main.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/main.c)):

```c
int main(int argc, char* argv[])
{
    tracy_manager_init_global();          // 1. Profiler bootstrap

    CliAction action = cli_handle_args(argc, argv);  // 2. CLI parsing
    if (action == CLI_ACTION_EXIT_SUCCESS) return EXIT_SUCCESS;
    if (action == CLI_ACTION_EXIT_FAILURE) return EXIT_FAILURE;

    // 3. SIMD-aligned allocation of the App structure
    App* app = (App*)platform_aligned_alloc(sizeof(App), SIMD_ALIGNMENT);
    *app = (App){0};

    // 4. Full initialization
    if (!app_init(app, WINDOW_WIDTH, WINDOW_HEIGHT, "Icosphere Phong"))
        { app_cleanup(app); platform_aligned_free(app); return EXIT_FAILURE; }

    // 5. Main loop
    app_run(app);

    // 6. Cleanup
    app_cleanup(app);
    platform_aligned_free(app);
    return EXIT_SUCCESS;
}
```

The design is **intentionally simple** — all complexity is encapsulated in `app_init()` → `app_run()` → `app_cleanup()`.

### Design Decisions

| Decision | Why? |
|----------|------|
| **SIMD-aligned allocation** | The `App` struct contains `mat4`/`vec3` fields (via *cglm*) that benefit from 16-byte alignment for SSE/NEON vectorization |
| **Zero-init** `{0}` | Deterministic state — every pointer starts `NULL`, every flag starts `0` |
| **Tracy first** | The profiler must be initialized before all other subsystems to capture the full timeline |
| **Single `App` struct** | All application state lives in one contiguous allocation — cache-friendly, easy to pass around |

<pre class="mermaid">
graph TD
    A("🚀 main()") --> B("app_init()")
    B --> B1("Window + OpenGL Context")
    B --> B2("Camera & Input")
    B --> B3("Scene — GPU Resources")
    B --> B4("Async Loader Thread")
    B --> B5("Post-Processing Pipeline")
    B --> B6("Profiling Systems")
    B1 & B2 & B3 & B4 & B5 & B6 --> C("app_run() — Main Loop")
    C --> C1("Poll Events")
    C1 --> C2("Camera Physics")
    C2 --> C3("renderer_draw_frame()")
    C3 --> C4("SwapBuffers")
    C4 -->|"next frame"| C1
    C --> D("app_cleanup()")
    D --> E("🏁 End")

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

## Chapter 2 — Opening a Window (GLFW + X11 + OpenGL)

The first real work happens in `window_create()` ([src/window.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/window.c)).

### 2.1 — GLFW Initialization and Window Hints

```c
glfwInit();
glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 4);
glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 4);          // OpenGL 4.4
glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
glfwWindowHint(GLFW_OPENGL_DEBUG_CONTEXT, GL_TRUE);     // Debug messages
glfwWindowHint(GLFW_SAMPLES, DEFAULT_SAMPLES);           // MSAA = 1 (off)
```

Behind the scenes, [GLFW](#glossary-glfw "C library for creating windows and handling keyboard/mouse input") performs a full **X11 handshake**:

<pre class="mermaid">
sequenceDiagram
    participant App as Application
    participant GLFW as GLFW
    participant X11 as X11 Server
    participant Mesa as Mesa/GPU Driver
    participant GPU as GPU

    App->>GLFW: glfwInit()
    GLFW->>X11: XOpenDisplay()
    X11-->>GLFW: Display* (connection)

    App->>GLFW: glfwCreateWindow(1920, 1080)
    GLFW->>X11: XCreateWindow() + GLX setup
    X11->>Mesa: glXCreateContextAttribsARB(4.4 Core, Debug)
    Mesa->>GPU: Allocate command buffer + context state
    Mesa-->>X11: GLXContext
    X11-->>GLFW: Window + Context ready

    App->>GLFW: glfwMakeContextCurrent()
    GLFW->>Mesa: glXMakeCurrent()
    Mesa->>GPU: Bind context to calling thread
</pre>

### 2.2 — GLAD: Loading OpenGL Function Pointers

```c
gladLoadGLLoader((GLADloadproc)glfwGetProcAddress);
```

OpenGL is **not a library** in the traditional sense — it's a *specification*. The actual function addresses live inside the GPU driver ([Mesa](#glossary-mesa "Open-source implementation of graphics APIs (OpenGL, Vulkan) on Linux"), NVIDIA, AMD). [GLAD](#glossary-glad "OpenGL loader generator — resolves GL function addresses at runtime") queries each address at runtime via `glXGetProcAddress` and populates a function pointer table. After this call, `glCreateShader`, `glDispatchCompute`, etc. become usable.

### 2.3 — OpenGL Debug Context

```c
setup_opengl_debug();
```

This enables `GL_DEBUG_OUTPUT_SYNCHRONOUS` and registers a callback that intercepts every GL error, warning, and performance hint. A hash table deduplicates messages (log only first occurrence).

### 2.4 — Input Capture and VSync

```c
glfwSwapInterval(0);                    // VSync OFF — unlimited FPS
glfwSetInputMode(app->window, GLFW_CURSOR, GLFW_CURSOR_DISABLED);  // FPS-style
```

The cursor is captured in **relative mode** — mouse movements produce delta offsets for orbit camera control.

---

## Chapter 3 — CPU-Side Initialization

Before touching the GPU, several CPU-side systems are bootstrapped.

### 3.1 — The Orbit Camera

```c
camera_init(&app->camera, 20.0F, -90.0F, 0.0F);
```

The camera starts at:

- **Distance**: 20 units from the origin
- **Yaw**: −90° (looking along −Z)
- **Pitch**: 0° (horizon level)
- **FOV**: 60° vertical
- **Z-clip**: [0.1, 1000.0]

It uses a **fixed-timestep physics model** (60 Hz) with exponential smoothing for rotation:

<pre class="mermaid">
graph LR
    subgraph "Camera Update Pipeline"
        A("Mouse Delta") -->|"EMA filter"| B("yaw_target / pitch_target")
        B -->|"Lerp α=0.1"| C("yaw / pitch (smoothed)")
        C --> D("camera_update_vectors()")
        D --> E("front, right, up vectors")
        E --> F("View Matrix (lookAt)")
    end

    subgraph "Physics (Fixed 60Hz)"
        G("WASD Keys") --> H("Target Velocity")
        H -->|"acceleration × dt"| I("Current Velocity")
        I -->|"friction"| J("Position += vel × dt")
        J --> K("Head bobbing (sine wave)")
    end

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444
    classDef loopNode fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d

    class D,F keyFunc
    class A,B,C,E subsystem
    class G,H,I,J,K loopNode
</pre>

### 3.2 — Async Loader Thread

```c
app->async_loader = async_loader_create(&app->tracy_mgr);
```

A dedicated **POSIX thread** is spawned for background I/O. It sleeps on a [condition variable](#glossary-condition-variable "Sync mechanism: a thread sleeps until another signals it") (`pthread_cond_wait`) until work is queued. This prevents disk reads from stalling the render loop.

<pre class="mermaid">
stateDiagram-v2
    [*] --> IDLE
    IDLE --> PENDING: async_loader_request()
    PENDING --> LOADING: Worker wakes up
    LOADING --> WAITING_FOR_PBO: I/O complete, needs GPU buffer
    WAITING_FOR_PBO --> CONVERTING: Main thread provides PBO
    CONVERTING --> READY: SIMD Float→Half conversion done
    READY --> IDLE: Main thread consumes result
</pre>

---

## Chapter 4 — Scene Initialization (The GPU Wakes Up)

`scene_init()` ([src/scene.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/scene.c)) is where the GPU gets its first real work.

### 4.1 — Default Scene State

```c
scene->subdivisions    = 3;                     // Icosphere level 3
scene->wireframe       = 0;                     // Solid fill
scene->show_envmap     = 1;                     // Skybox visible
scene->billboard_mode  = 1;                     // Transparent spheres (billboard)
scene->sorting_mode    = SORTING_MODE_GPU_BITONIC;  // GPU sorting
scene->gi_mode         = GI_MODE_OFF;           // No GI
scene->specular_aa_enabled = 1;                 // Curvature-based AA
```

### 4.2 — Dummy Textures and BRDF LUT

Two sentinel textures are created immediately — they serve as **fallbacks** whenever an [IBL](#glossary-ibl "Image-Based Lighting — lighting extracted from a panoramic HDR environment image") texture isn't ready:

```c
scene->dummy_black_tex = render_utils_create_color_texture(0.0, 0.0, 0.0, 0.0);  // 1×1 RGBA
scene->dummy_white_tex = render_utils_create_color_texture(1.0, 1.0, 1.0, 1.0);  // 1×1 RGBA
```

Then the **[BRDF LUT](#glossary-brdf-lut "Pre-computed texture encoding the BRDF integral for all (angle, roughness) combinations")** (Look-Up Table) is generated once via [compute shader](#glossary-compute-shader "General-purpose GPU shader outside the rendering pipeline"):

```c
scene->brdf_lut_tex = build_brdf_lut_map(512);
```

| Property | Value |
|----------|-------|
| Size | 512 × 512 |
| Format | `GL_RG16F` (2 channels, 16-bit float each) |
| Content | Pre-integrated split-sum BRDF (Schlick-GGX) |
| Shader | `shaders/IBL/spbrdf.glsl` (compute) |
| Work groups | 16 × 16 (512/32 per axis) |

This texture maps `(NdotV, roughness)` → `(F0_scale, F0_bias)` and is used every frame by the [PBR](#glossary-pbr "Physically-Based Rendering — lighting model that simulates real physics of light") [fragment shader](#glossary-fragment-shader "Shader that computes the color of each on-screen pixel") to avoid expensive real-time [BRDF](#glossary-brdf "Bidirectional Reflectance Distribution Function — describes how light bounces off a surface") integration.

### 4.3 — Two Rendering Modes: Billboard Ray-Tracing vs. Icosphere Mesh

The engine supports two sphere rendering strategies. The **default** is [billboard](#glossary-billboard "Screen-facing quad used here as a ray-tracing surface") [ray-tracing](#glossary-ray-tracing "Technique that traces light rays to compute intersections with objects").

#### Default: Billboard + Per-Pixel Ray-Tracing (billboard_mode = 1)

Each sphere is rendered as a **single screen-aligned quad** (4 vertices, 2 triangles). The fragment [shader](#glossary-shader "Program executed directly on the GPU (vertex, fragment, compute)") performs an **analytical ray-sphere intersection** per pixel, producing mathematically perfect spheres.

![Billboard AABB geometry — the projected quad encloses the sphere on screen]({static}/images/suckless-ogl/billboard_aabb_geometry.png)
*<center>The [vertex shader](#glossary-vertex-shader "Shader that processes each geometry vertex (position, projection)") projects a tight [quad](#glossary-quad "Rectangle made of 2 triangles — the basic 2D primitive") around the sphere's screen-space bounding box via analytical tangent-line computation.</center>*

**Advantages**:

- Pixel-perfect silhouettes (no polygon faceting, ever)
- Correct per-pixel depth (`gl_FragDepth` written from the ray hit point)
- Analytically smooth normals (normalized `hitPos − center`)
- Edge anti-aliasing via smooth [discriminant](#glossary-discriminant "Mathematical value (b²−c) determining whether a ray hits a sphere") falloff
- True alpha transparency (glass-like, with [back-to-front](#glossary-back-to-front "Rendering order from farthest to nearest, required for correct transparency") sorting)

<pre class="mermaid">
graph LR
    subgraph "Billboard Ray-Tracing (Default)"
        A("4-vertex Quad<br/>(per instance)") -->|"Vertex Shader:<br/>project to sphere bounds"| B("Screen-space quad")
        B -->|"Fragment Shader:<br/>ray-sphere intersection"| C("Perfect sphere<br/>per-pixel normal + depth")
    end

    subgraph "Icosphere Mesh (Fallback)"
        D("642-vertex mesh<br/>(subdivided icosahedron)") -->|"Rasterized as<br/>triangles"| E("Polygon approximation<br/>(faceted at low subdiv)")
    end

    classDef highlight fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef fallback fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#666666

    class A,B,C highlight
    class D,E fallback
</pre>

> **💡 Why Billboard Ray-Tracing?** With 100 spheres, the billboard approach uses **100 × 4 = 400 vertices** total, versus **100 × 642 = 64,200 vertices** for level-3 icospheres. More importantly, the spheres are **mathematically perfect** at every zoom level — no [tessellation](#glossary-tessellation "Subdividing geometry into finer triangles for more detail") artifacts.

#### Fallback: Instanced Icosphere Mesh (billboard_mode = 0)

The [icosphere](#glossary-icosphere "Sphere built by subdividing an icosahedron (20 faces) — more uniform than a UV sphere") path generates a recursively subdivided icosahedron:

<pre class="mermaid">
graph LR
    A("Level 0<br/>12 vertices<br/>20 triangles") -->|"Subdivide"| B("Level 1<br/>42 vertices<br/>80 triangles")
    B -->|"Subdivide"| C("Level 2<br/>162 vertices<br/>320 triangles")
    C -->|"Subdivide"| D("Level 3<br/>642 vertices<br/>1,280 triangles")
    D -->|"..."| E("Level 6<br/>~40k vertices")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class D keyFunc
    class A,B,C,E subsystem
</pre>

### 4.4 — Material Library

```c
scene->material_lib = material_load_presets("assets/materials/pbr_materials.json");
```

The JSON file defines **101 PBR material presets** organized by category:

| Category | Examples | Metallic | Roughness |
|----------|----------|----------|-----------|
| **Pure Metals** | Gold, Silver, Copper, Chrome | 1.0 | 0.05–0.2 |
| **Weathered Metals** | Rusty Iron, Oxidized Copper | 0.7–0.95 | 0.4–0.8 |
| **Glossy Dielectrics** | Colored Plastics | 0.0 | 0.05–0.15 |
| **Matte Materials** | Fabric, Clay, Sand | 0.0 | 0.65–0.95 |
| **Stones** | Granite, Marble, Obsidian | 0.0 | 0.35–0.85 |
| **Organics** | Oak, Leather, Bone | 0.0 | 0.35–0.75 |
| **Paints** | Car Paint, Pearl, Satin | 0.3–0.7 | 0.1–0.5 |
| **Technical** | Rubber, Carbon, Ceramic | 0.0–0.1 | 0.05–0.85 |

Each material provides: `albedo` (RGB), `metallic` (0–1), `roughness` (0–1).

### 4.5 — The Instance Grid

```c
const int cols    = 10;       // DEFAULT_COLS
const float spacing = 2.5F;   // DEFAULT_SPACING
```

A **10×10 grid of 100 spheres** is laid out in the XY plane, centered at the origin:

```
Grid dimensions:
  Width  = (10 - 1) × 2.5 = 22.5 units
  Height = (10 - 1) × 2.5 = 22.5 units
  Z = 0 (all spheres in the same plane)
```

Each instance stores **88 bytes**:

```c
typedef struct SphereInstance {
    mat4  model;      // 64 bytes — 4×4 transform matrix
    vec3  albedo;     // 12 bytes — RGB color
    float metallic;   //  4 bytes
    float roughness;  //  4 bytes
    float ao;         //  4 bytes — always 1.0
} SphereInstance;     // Total: 88 bytes per instance
```

### 4.6 — VAO Layout (Billboard Mode)

In billboard mode, the [VAO](#glossary-vao "Vertex Array Object — describes the format of geometric data sent to the GPU") binds a **4-vertex quad** and per-instance material data:

```
┌────────────────────────────────────────────────────────────────┐
│              Billboard VAO (Default Rendering Mode)            │
├────────────┬────────────┬─────────────────────────────────────┤
│  Location  │  Source    │  Description                        │
├────────────┼────────────┼─────────────────────────────────────┤
│  0         │  Quad VBO  │  vec3 position   (±0.5 quad verts)  │
│  1         │  Quad VBO  │  vec3 normal     (stub, unused)     │
│  2–5       │  Inst VBO  │  mat4 model      (per-instance)     │
│  6         │  Inst VBO  │  vec3 albedo     (per-instance)     │
│  7         │  Inst VBO  │  vec3 pbr (M,R,AO) (per-instance)   │
└────────────┴────────────┴─────────────────────────────────────┘

Location 0–1: glVertexAttribDivisor = 0 (advance per vertex, 4 verts)
Location 2–7: glVertexAttribDivisor = 1 (advance per instance)
```

**Draw call**: `glDrawArraysInstanced(GL_TRIANGLE_STRIP, 0, 4, 100)` — 100 quads, face culling disabled.

### 4.7 — Shader Compilation

All shaders are compiled during `scene_init()`. The loader ([src/shader.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/shader.c)) supports a custom **`@header` include system**:

```glsl
// In pbr_ibl_instanced.frag:
@header "pbr_functions.glsl"
@header "sh_probe.glsl"
```

This recursively inlines files (max depth: 16) with include-guard deduplication.

<pre class="mermaid">
graph TD
    INIT("scene_init() — Shader Compilation") --> REND
    INIT --> COMP
    INIT --> POST

    subgraph REND ["🎨 Rendering Programs"]
        direction TB
        PBR("PBR Instanced — pbr_ibl_instanced.vert/.frag")
        BB("PBR Billboard — pbr_ibl_billboard.vert/.frag")
        SKY("Skybox — background.vert/.frag")
        UI("UI Overlay — ui.vert/.frag")
    end

    subgraph COMP ["⚡ Compute Shaders"]
        direction TB
        SPMAP("Specular Prefilter — IBL/spmap.glsl")
        IRMAP("Irradiance Conv. — IBL/irmap.glsl")
        BRDF("BRDF LUT — IBL/spbrdf.glsl")
        LUM("Luminance Reduction — IBL/luminance_reduce")
    end

    subgraph POST ["✨ Post-Process"]
        direction TB
        PP("Final Composite — postprocess.vert/.frag")
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

## Chapter 5 — Post-Processing Pipeline Setup

```c
postprocess_init(&app->postprocess, &app->gpu_profiler, 1920, 1080);
```

### 5.1 — The Scene FBO (Multi-Render Target)

The main offscreen framebuffer uses **[MRT](#glossary-mrt "Multiple Render Targets — write to several textures in a single render pass")** (Multiple Render Targets):

| Attachment | Format | Size | Purpose |
|-----------|--------|------|---------|
| `GL_COLOR_ATTACHMENT0` | `GL_RGBA16F` | 1920×1080 | HDR scene color (alpha = luma for FXAA) |
| `GL_COLOR_ATTACHMENT1` | `GL_RG16F` | 1920×1080 | Per-pixel velocity for motion blur |
| `GL_DEPTH_STENCIL_ATTACHMENT` | `GL_DEPTH32F_STENCIL8` | 1920×1080 | Depth buffer + stencil mask |
| Stencil view | `GL_R8UI` | 1920×1080 | Read-only stencil as texture |

<pre class="mermaid">
graph TD
    FBO("Scene FBO — Multi-Render Target") --> C0
    FBO --> C1
    FBO --> DS
    DS --> SV

    C0("🟦 Color 0 — GL_RGBA16F<br/>HDR Scene Color")
    C1("🟩 Color 1 — GL_RG16F<br/>Velocity Vectors")
    DS("🟫 Depth/Stencil — GL_DEPTH32F_STENCIL8")
    SV("🟪 Stencil View — GL_R8UI (TextureView)")

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

### 5.2 — Sub-Effect Resources

Each post-processing effect initializes its own resources:

| Effect | GPU Resources |
|--------|--------------|
| **Bloom** | Mip-chain FBOs (6 levels), prefilter/downsample/upsample textures |
| **DoF** | Blur texture, CoC (Circle of Confusion) texture |
| **Auto-Exposure** | Luminance downsample texture, 2× PBOs (readback), 2× GLSync fences |
| **Motion Blur** | Tile-max velocity texture (compute), neighbor-max texture (compute) |
| **3D LUT** | 32³ `GL_TEXTURE_3D` loaded from `.cube` files |

### 5.3 — Default Active Effects

```c
postprocess_enable(&app->postprocess, POSTFX_FXAA);  // Only FXAA
```

On startup, only **[FXAA](#glossary-fxaa "Fast Approximate Anti-Aliasing — fast post-process anti-aliasing on the final image")** is active. Other effects are toggled at runtime via keyboard shortcuts.

---

## Chapter 6 — The First HDR Environment Load

```c
env_manager_load(&app->env_mgr, app->async_loader, "env.hdr");
```

This triggers the **asynchronous environment loading pipeline** — the most complex multi-frame operation in the engine.

### 6.1 — Async Loading Sequence

<pre class="mermaid">
sequenceDiagram
    participant Main as Main Thread (Render)
    participant Worker as Async Worker Thread
    participant GPU as GPU

    Main->>Worker: async_loader_request("env.hdr")
    Note over Worker: State: PENDING → LOADING
    Worker->>Worker: stbi_loadf() — decode HDR to float RGBA
    Note over Worker: ~50ms for 2K HDR on NVMe

    Worker-->>Main: State: WAITING_FOR_PBO
    Main->>GPU: glGenBuffers() → PBO
    Main->>GPU: glMapBuffer(PBO, WRITE)
    Main-->>Worker: async_loader_provide_pbo(pbo_ptr)

    Note over Worker: State: CONVERTING
    Worker->>Worker: SIMD float32 → float16 conversion
    Note over Worker: ~2ms for 2048×1024

    Worker-->>Main: State: READY
    Main->>GPU: glUnmapBuffer(PBO)
    Main->>GPU: glTexSubImage2D(from PBO)
    Note over GPU: DMA transfer: PBO → VRAM
    Main->>GPU: glGenerateMipmap()
</pre>

### 6.2 — Transition State Machine

During the first load, the screen stays **black** (no crossfade from a previous scene):

<pre class="mermaid">
stateDiagram-v2
    [*] --> WAIT_IBL: "First load"
    WAIT_IBL --> WAIT_IBL: "IBL in progress..."
    WAIT_IBL --> FADE_IN: "IBL complete"
    FADE_IN --> IDLE: "Alpha reaches 0"
</pre>

**`WAIT_IBL`**: `transition_alpha = 1.0` (fully opaque black) — the screen is black during the first few frames.

**`FADE_IN`**: Alpha decreases from 1.0 → 0.0 over 250ms.

---

## Chapter 7 — IBL Generation (Progressive, Multi-Frame)

Once the [HDR](#glossary-hdr "High Dynamic Range — color values exceeding 1.0 (realistic light intensities)") texture is uploaded, the **IBL Coordinator** ([src/ibl_coordinator.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/ibl_coordinator.c)) takes over. It computes three maps across multiple frames to avoid GPU stalls.

### 7.1 — The Three IBL Maps

<pre class="mermaid">
graph TB
    HDR("HDR Environment Map<br/>2048×1024 equirectangular<br/>GL_RGBA16F") --> SPEC
    HDR --> IRR
    HDR --> LUM

    SPEC("Specular Prefilter Map<br/>1024×1024 × 5 mip levels<br/>Compute: spmap.glsl")
    IRR("Irradiance Map<br/>64×64<br/>Compute: irmap.glsl")
    LUM("Luminance Reduction<br/>1×1 average<br/>Compute: luminance_reduce")

    SPEC -->|"Per-pixel reflection<br/>roughness → mip level"| PBR("PBR Shader")
    IRR -->|"Diffuse hemisphere<br/>integral"| PBR
    LUM -->|"Auto exposure<br/>threshold"| PP("Post-Process")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef compute fill:#f3e5f5,stroke:#ab47bc,stroke-width:1.5px,color:#2d2d2d
    classDef target fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d

    class HDR keyFunc
    class SPEC,IRR,LUM compute
    class PBR,PP target
</pre>

| Map | Resolution | Format | Mip Levels | Compute Shader |
|-----|-----------|--------|------------|----------------|
| **Specular Prefilter** | 1024×1024 | `GL_RGBA16F` | 5 | `IBL/spmap.glsl` |
| **Irradiance** | 64×64 | `GL_RGBA16F` | 1 | `IBL/irmap.glsl` |
| **Luminance** | 1×1 | `GL_R32F` | 1 | `IBL/luminance_reduce_pass1/2.glsl` |

### 7.2 — Progressive Slicing Strategy

To avoid frame spikes, each mip level is subdivided into **slices** processed over consecutive frames:

| IBL Stage | Hardware GPU | Software GPU (llvmpipe) |
|-----------|-------------|------------------------|
| Specular Mip 0 (1024²) | 24 slices (42 rows each) | 1 slice (full) |
| Specular Mip 1 (512²) | 8 slices | 1 slice |
| Specular Mips 2–4 | Grouped (1 dispatch) | 1 slice |
| Irradiance (64²) | 12 slices | 1 slice |
| Luminance | 2 dispatches (pass 1 + 2) | 2 dispatches |

<pre class="mermaid">
gantt
    title Progressive IBL Generation Timeline
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
    Grouped dispatch       :m3, 9000, 10000

    section Irradiance
    Slices 1-12            :i1, 10000, 12000

    section Done
    IBL Complete → Fade In :ibl_done, 12000, 13000
</pre>

### 7.3 — IBL State Machine

```c
enum IBLState {
    IBL_STATE_IDLE,             // No work
    IBL_STATE_LUMINANCE,        // Pass 1: luminance reduction
    IBL_STATE_LUMINANCE_WAIT,   // Wait for readback fence
    IBL_STATE_SPECULAR_INIT,    // Allocate specular texture
    IBL_STATE_SPECULAR_MIPS,    // Progressive mip generation
    IBL_STATE_IRRADIANCE,       // Progressive irradiance convolution
    IBL_STATE_DONE              // All maps ready
};
```

---

## Chapter 8 — The Main Loop

`app_run()` ([src/app.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/app.c)) is the heartbeat — a classic **uncapped game loop** with fixed-timestep physics.

<pre class="mermaid">
graph TD
    A("① glfwPollEvents() — Keyboard, mouse, resize")
    A --> B("② Time & FPS — delta_time, frame_count")
    B --> C("③ Camera Physics — Fixed 60Hz, smooth rotation lerp")
    C --> D("④ Geometry Update — if subdivisions changed")
    D --> E("⑤ app_update() — Process input state")
    E --> F("⑥ renderer_draw_frame() — THE BIG ONE")
    F --> G("⑦ Tracy screenshots — profiling")
    G --> H("⑧ glfwSwapBuffers() — Present to screen")
    H -->|"next frame"| A

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef loopNode fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class F keyFunc
    class A,B,C,D,E,G loopNode
    class H subsystem
</pre>

### 8.1 — Deferred Resize

Window resize events are **deferred** — the [GLFW](#glossary-glfw "C library for creating windows and handling keyboard/mouse input") callback only records the new dimensions. The actual [FBO](#glossary-fbo "Framebuffer Object — offscreen render surface (draw to it instead of the screen)") recreation happens at the start of the next frame, outside the callback's limited context.

### 8.2 — Camera Fixed-Timestep Integration

```c
app->camera.physics_accumulator += (float)app->delta_time;
while (app->camera.physics_accumulator >= app->camera.fixed_timestep) {
    camera_fixed_update(&app->camera);  // Velocity, friction, bobbing
    app->camera.physics_accumulator -= app->camera.fixed_timestep;
}

// Smooth rotation (exponential interpolation)
float alpha = app->camera.rotation_smoothing;  // ~0.1
app->camera.yaw   += (app->camera.yaw_target   - app->camera.yaw)   * alpha;
app->camera.pitch += (app->camera.pitch_target - app->camera.pitch) * alpha;
camera_update_vectors(&app->camera);
```

This ensures deterministic physics regardless of frame rate, while rotation stays smooth via per-frame interpolation.

---

## Chapter 9 — Rendering a Frame

`renderer_draw_frame()` ([src/renderer.c](https://github.com/yoyonel/suckless-ogl/blob/master/src/renderer.c)) orchestrates the full rendering pipeline.

### 9.1 — High-Level Architecture

<pre class="mermaid">
graph TD
    A("GPU Profiler Begin") --> B("postprocess_begin() — Bind Scene FBO, Clear")
    B --> C("camera_get_view_matrix()")
    C --> D("glm_perspective() — FOV=60°, near=0.1, far=1000")
    D --> E("ViewProj = Proj × View")
    E --> G1("🌅 Pass 1: Skybox — depth disabled")
    G1 --> G2("🔢 Pass 2: Sphere Sorting — GPU Bitonic")
    G2 --> G3("🔮 Pass 3: PBR Spheres — instanced billboard draw")
    G3 --> H("✨ postprocess_end() — 7-Stage Pipeline")
    H --> I("🖥️ UI Overlay + Env Transition")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef loopNode fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef setup fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444
    classDef postfx fill:#fce4ec,stroke:#c2185b,stroke-width:1.5px,color:#2d2d2d

    class G1,G2,G3 keyFunc
    class A,B,C,D,E setup
    class H,I postfx
</pre>

### 9.2 — Pass 1: Skybox

The [skybox](#glossary-skybox "Panoramic image displayed as scene background (sky/environment)") is drawn **first**, with depth testing **disabled**. It uses a fullscreen [quad](#glossary-quad "Rectangle made of 2 triangles — the basic 2D primitive") trick:

```glsl
// background.vert — reconstruct world-space ray
gl_Position = vec4(in_position.xy, 1.0, 1.0);  // Depth = 1.0 (far plane)
vec4 pos = m_inv_view_proj * vec4(in_position.xy, 1.0, 1.0);
RayDir = pos.xyz / pos.w;  // Reconstructed world-space ray
```

```glsl
// background.frag — equirectangular sampling of the HDR
vec2 uv = SampleEquirectangular(normalize(RayDir));
vec3 envColor = textureLod(environmentMap, uv, blur_lod).rgb;
envColor = clamp(envColor, vec3(0.0), vec3(200.0));  // NaN protection + anti-fireflies
FragColor = vec4(envColor, luma);  // Alpha = luma for FXAA
VelocityOut = vec2(0.0);          // No motion for skybox
```

### 9.3 — Pass 2: Sphere Sorting (GPU Bitonic Sort)

For transparent [billboard](#glossary-billboard "Screen-facing quad used here as a ray-tracing surface") rendering, spheres must be drawn **back-to-front**:

| Mode | Where | Algorithm | Complexity |
|------|-------|-----------|------------|
| `CPU_QSORT` | CPU | `qsort()` (stdlib) | O(n·log n) avg |
| `CPU_RADIX` | CPU | Radix sort | O(n·k) |
| `GPU_BITONIC` ★ | GPU | Bitonic merge sort (compute) | O(n·log²n) |

### 9.4 — Pass 3: PBR Spheres — Billboard Ray-Tracing

This is the core rendering pass. **A single [draw call](#glossary-draw-call "A CPU→GPU call requesting geometry rendering") renders all 100 spheres**:

| Metric | Value |
|--------|-------|
| Vertices per sphere | **4** (billboard quad) |
| Triangles per sphere | 2 (triangle strip) |
| Instances | 100 (10×10 grid) |
| **Total vertices** | **400** |
| **Draw calls** | **1** |
| Sphere precision | **Mathematically perfect** (ray-traced) |

### 9.5 — The Billboard Fragment Shader (Ray-Sphere Intersection)

The [fragment shader](#glossary-fragment-shader "Shader that computes the color of each on-screen pixel") (`pbr_ibl_billboard.frag`) is where the real magic happens. Instead of shading a rasterized [mesh](#glossary-mesh "Collection of triangles forming a 3D object"), it **analytically intersects a ray with a perfect sphere**:

![Ray-sphere intersection — the geometric principle]({static}/images/suckless-ogl/sphere_intersection.jpg)
*<center>Analytical ray-sphere intersection: the [discriminant](#glossary-discriminant "Mathematical value (b²−c) determining whether a ray hits a sphere") determines whether the pixel hits the sphere.</center>*

```glsl
// Analytical ray-sphere intersection
vec3 oc = rayOrigin - center;
float b = dot(oc, rayDir);
float c = dot(oc, oc) - radius * radius;
float discriminant = b * b - c;  // >0 = hit, <0 = miss
if (discriminant < 0.0) discard;
float t = -b - sqrt(discriminant);  // nearest intersection
vec3 hitPos = rayOrigin + t * rayDir;
vec3 N = normalize(hitPos - center);  // perfect analytic normal
```

<pre class="mermaid">
graph TD
    R("🔦 Build Ray — origin=camPos, dir=normalize(WorldPos-camPos)")
    R --> INT("📐 Ray-Sphere Intersection — discriminant = b² - c")
    INT --> HIT{"Hit?"}
    HIT -->|"No — disc < 0"| DISCARD("❌ discard — pixel outside sphere")
    HIT -->|"Yes"| HITPOS("✅ hitPos = origin + t × dir")
    HITPOS --> NORMAL("N = normalize(hitPos - center) — perfect normal")
    HITPOS --> DEPTH("gl_FragDepth = project(hitPos) — correct Z-buffer")
    NORMAL --> PBR("V = -rayDir")
    PBR --> FRESNEL("Fresnel-Schlick")
    PBR --> GGX("Smith-GGX Geometry")
    PBR --> NDF("GGX NDF Distribution")
    FRESNEL & GGX & NDF --> SPEC("IBL Specular — prefilterMap × brdfLUT")
    PBR --> DIFF("IBL Diffuse — irradiance(N) × albedo")
    SPEC & DIFF --> FINAL("color = Diffuse + Specular")
    FINAL --> AA("Edge Anti-Aliasing — smoothstep on discriminant")
    AA --> ALPHA("FragColor = vec4(color, edgeFactor) — premultiplied alpha")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef compute fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef entryExit fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class R,INT,HIT keyFunc
    class HITPOS,NORMAL,DEPTH,PBR compute
    class FRESNEL,GGX,NDF,SPEC,DIFF subsystem
    class FINAL,AA,ALPHA,DISCARD entryExit
</pre>

#### Analytical Edge Anti-Aliasing

![Analytical anti-aliasing of spheres — smoothstep on the discriminant]({static}/images/suckless-ogl/sphere_analytic_aa.jpg)
*<center>Analytical anti-aliasing uses the discriminant as a distance-to-edge metric — no [MSAA](#glossary-msaa "Multisample Anti-Aliasing — geometric anti-aliasing (expensive, avoided here)") needed for smooth edges.</center>*

```glsl
float pixelSizeWorld = (2.0 * clipW) / (proj[1][1] * screenHeight);
float edgeFactor = smoothstep(0.0, 1.0, discriminant / (2.0 * radius * pixelSizeWorld));
FragColor = vec4(color * edgeFactor, edgeFactor);  // premultiplied alpha
```

![Detail of perfect sphere anti-aliasing]({static}/images/suckless-ogl/sphere_perfect_aa_detail.jpg)
*<center>Close-up detail: sphere edges are perfectly smooth thanks to analytical [ray-tracing](#glossary-ray-tracing "Technique that traces light rays to compute intersections with objects").</center>*

#### Billboard Projection

![Sphere AABB projection optimization]({static}/images/suckless-ogl/sphere_aabb_optimization_projective.png)
*<center>The [vertex shader](#glossary-vertex-shader "Shader that processes each geometry vertex (position, projection)") computes a tight screen-space quad via analytical tangent-line projection, handling 3 cases: camera outside, inside, or behind the sphere.</center>*

---

## Chapter 10 — Post-Processing Pipeline

After the 3D scene is rendered into the [MRT](#glossary-mrt "Multiple Render Targets — write to several textures in a single render pass") [FBO](#glossary-fbo "Framebuffer Object — offscreen render surface (draw to it instead of the screen)"), `postprocess_end()` applies up to **8 effects** in a carefully ordered pipeline.

### 10.1 — The 7-Stage Pipeline

<pre class="mermaid">
graph TD
    A("Memory Barrier — flush MRT writes")
    A --> B("① Bloom — Downsample → Threshold → Upsample")
    B --> C("② Depth of Field — CoC → Bokeh blur")
    C --> D("③ Auto-Exposure — Luminance reduction → PBO readback")
    D --> E("④ Motion Blur — Tile-max velocity → Neighbor-max")
    E --> F("⑤ Bind 9 Textures + Upload UBO")
    F --> H("Draw fullscreen quad")
    H --> J("Vignette")
    J --> K("Film Grain")
    K --> L("White Balance")
    L --> M("Color Grading — Sat, Contrast, Gamma, Gain")
    M --> N("Tonemapping — filmic curve")
    N --> O("3D LUT Grading")
    O --> P("FXAA")
    P --> Q("Dithering — anti-banding")
    Q --> R("Atmospheric Fog")

    classDef keyFunc fill:#fff59d,stroke:#f9a825,stroke-width:2px,color:#2d2d2d
    classDef compute fill:#f3e5f5,stroke:#ab47bc,stroke-width:1.5px,color:#2d2d2d
    classDef shader fill:#e3f2fd,stroke:#42a5f5,stroke-width:1.5px,color:#2d2d2d
    classDef subsystem fill:#ffffff,stroke:#aaaaaa,stroke-width:1.5px,color:#444444

    class A,F,H subsystem
    class B,C,D,E compute
    class J,K,L,M,N,O,P,Q,R shader
</pre>

### 10.2 — Post-Processing Effects Gallery

Here is the **front view** render with different effects enabled individually — each image shows a single effect applied to the same scene:

#### No post-processing (raw)
![Raw render without any post-processing]({static}/images/suckless-ogl/ref_front_subtle_none.png)
*<center>Raw image from the [PBR](#glossary-pbr "Physically-Based Rendering — lighting model that simulates real physics of light") renderer — no post-processing applied.</center>*

#### FXAA (fast anti-aliasing)
![Render with FXAA enabled]({static}/images/suckless-ogl/ref_front_subtle_fxaa.png)
*<center>[FXAA](#glossary-fxaa "Fast Approximate Anti-Aliasing — fast post-process anti-aliasing on the final image") (Fast Approximate Anti-Aliasing) — smooths edges without the cost of [MSAA](#glossary-msaa "Multisample Anti-Aliasing — geometric anti-aliasing (expensive, avoided here)").</center>*

#### Bloom
![Render with Bloom enabled]({static}/images/suckless-ogl/ref_front_subtle_bloom.png)
*<center>[Bloom](#glossary-bloom "Glow halo around very bright areas (lens light diffusion)") — bright areas bleed outward, simulating lens light diffusion.</center>*

#### Depth of Field
![Render with Depth of Field enabled]({static}/images/suckless-ogl/ref_front_subtle_dof.png)
*<center>Depth of Field — objects out of focus are blurred like with a real lens.</center>*

#### Auto-Exposure
![Render with Auto-Exposure enabled]({static}/images/suckless-ogl/ref_front_subtle_auto_exposure.png)
*<center>[Auto-exposure](#glossary-auto-exposure "Automatic scene brightness adaptation (simulates the eye's iris)") — the engine adapts exposure like the human eye adjusting to brightness.</center>*

#### Motion Blur
![Render with Motion Blur enabled]({static}/images/suckless-ogl/ref_front_subtle_motion_blur.png)
*<center>Per-pixel [motion blur](#glossary-motion-blur "Per-pixel motion blur simulating a camera shutter") — uses velocity vectors to simulate cinematic motion blur.</center>*

#### Sony A7S III Cinematic Profile
![Render with Sony A7S III profile]({static}/images/suckless-ogl/ref_front_sony_a7siii.png)
*<center>Full Sony A7S III photographic profile — [color grading](#glossary-color-grading "Creative color adjustments (saturation, contrast, gamma, hue)"), white balance, exposure, and [3D LUT](#glossary-3d-lut "3D color lookup table for a cinematic &quot;look&quot; (`.cube` file)") combined for a cinematic look.</center>*

### 10.3 — Shader Optimization via Conditional Compilation

The post-process [fragment shader](#glossary-fragment-shader "Shader that computes the color of each on-screen pixel") uses **compile-time #defines** to eliminate branches:

```glsl
#ifdef OPT_ENABLE_BLOOM
    color += bloomTexture * bloomIntensity;
#endif

#ifdef OPT_ENABLE_FXAA
    color = fxaa(color, uv, texelSize);
#endif
```

A 32-entry **LRU cache** stores compiled [shader](#glossary-shader "Program executed directly on the GPU (vertex, fragment, compute)") variants for different effect flag combinations. Switching effects triggers lazy recompilation only for new combinations.

### 10.4 — Tonemapping Curves

![Tonemapping curves comparison]({static}/images/suckless-ogl/tonemapping_curves.png)
*<center>Comparison of available [tonemapping](#glossary-tonemapping "Conversion of HDR colors (unbounded) to displayable LDR (0–255)") curves — the transformation from linear [HDR](#glossary-hdr "High Dynamic Range — color values exceeding 1.0 (realistic light intensities)") to displayable LDR.</center>*

### 10.5 — Exposure Adaptation

![Exposure adaptation over time]({static}/images/suckless-ogl/exposure_adaptation.jpg)
*<center>Auto-exposure progressively adapts frame brightness, like the eye's iris adjusting to light.</center>*

---

## Chapter 11 — The First Visible Frame

Let's trace what actually appears on screen during the first seconds:

### Startup Timeline

| Frames | What Happens | On Screen |
|--------|-------------|-----------|
| **1–2** | Async loader reads `env.hdr` from disk | Black screen (`transition_alpha = 1.0`) |
| **3–4** | PBO → GPU texture transfer (DMA) + mipmap generation | Black screen |
| **5–15** | Progressive IBL computation (luminance, specular, irradiance) | Black screen (but spheres are rendered into FBO) |
| **~16** | IBL complete → `TRANSITION_FADE_IN` | Fade-in begins |
| **~20+** | Transition complete — steady state | Fully-lit PBR scene |

### Steady-State Frame

| Step | Detail | Time |
|------|--------|------|
| **1. Poll Events** | `glfwPollEvents()` | ~0.1ms CPU |
| **2. Camera Update** | 60Hz physics + rotation lerp | ~0.01ms CPU |
| **3a. Skybox** | Fullscreen quad, equirect. sampling | ~0.2ms GPU |
| **3b. Bitonic Sort** | Compute shader, 100 spheres | ~0.1ms GPU |
| **3c. Billboard Spheres** | 100 ray-traced quads, 1 draw call | ~0.5ms GPU |
| **4a. Bloom** | Downsample → Upsample (if enabled) | ~0.3ms GPU |
| **4b. DoF** | CoC → Bokeh blur (if enabled) | ~0.2ms GPU |
| **4c. Auto-Exposure** | Luminance reduction | ~0.1ms GPU |
| **4d. Motion Blur** | Tile-max velocity (if enabled) | ~0.2ms GPU |
| **4e. Final Composite** | 9 textures, UBO, fullscreen quad | ~0.3ms GPU |
| **5. UI Overlay** | Text + profiler + transition | ~0.1ms GPU |
| **6. SwapBuffers** | Present to screen | (wait) |
| | **Typical frame time** | **1–3ms GPU** |

---

## Chapter 12 — GPU Memory Budget

Here's an estimate of [VRAM](#glossary-vram "Dedicated GPU memory — where textures and buffers reside") consumption at steady state:

### Textures

| Resource | Resolution | Format | Size |
|----------|-----------|--------|------|
| HDR Environment | 2048×1024 | `GL_RGBA16F` | ~16 MB (with mips) |
| Specular Prefilter | 1024² × 5 mips | `GL_RGBA16F` | ~10.5 MB |
| Irradiance | 64×64 | `GL_RGBA16F` | ~32 KB |
| BRDF LUT | 512×512 | `GL_RG16F` | ~1 MB |
| Scene Color (FBO) | 1920×1080 | `GL_RGBA16F` | ~16 MB |
| Velocity (FBO) | 1920×1080 | `GL_RG16F` | ~8 MB |
| Depth/Stencil (FBO) | 1920×1080 | `GL_DEPTH32F_STENCIL8` | ~10 MB |
| Bloom chain (6 mips) | Various | `GL_RGBA16F` | ~21 MB |
| DoF blur | 1920×1080 | `GL_RGBA16F` | ~16 MB |
| Auto-Exposure | 64×64 → 1×1 | `GL_R32F` | ~16 KB |
| SH Probes (7 tex) | 21×21×3 | `GL_RGBA16F` | ~74 KB |

### Buffers

| Resource | Count | Size Each | Total |
|----------|-------|-----------|-------|
| Billboard quad VBO | 4 verts | 12 B (vec3) | 48 B |
| Instance VBO | 100 instances | ~88 B | ~8.6 KB |
| Sort SSBO | 100 entries | 8 B | ~800 B |
| Fullscreen quad VBO | 6 verts | 20 B | 120 B |
| UBO (post-process) | 1 | ~256 B | 256 B |

### Total Estimate

| Category | Approximate |
|----------|------------|
| Textures | ~99 MB |
| Buffers | ~40 KB |
| Shaders (compiled) | ~2 MB |
| **Total** | **~101 MB VRAM** |

> **💡 Dominant Cost**: The [HDR](#glossary-hdr "High Dynamic Range — color values exceeding 1.0 (realistic light intensities)") environment map + [bloom](#glossary-bloom "Glow halo around very bright areas (lens light diffusion)") chain + scene FBOs dominate VRAM usage. The geometry itself (100 [billboard](#glossary-billboard "Screen-facing quad used here as a ray-tracing surface") quads × 4 vertices in default mode) is negligible — the real sphere computation happens in the [fragment shader](#glossary-fragment-shader "Shader that computes the color of each on-screen pixel") via [ray-tracing](#glossary-ray-tracing "Technique that traces light rays to compute intersections with objects").

---

## Gallery: Multi-Angle Views

The engine supports automated captures from different camera angles, used for visual regression testing:

<table style="width:100%; border-collapse:collapse; border:none;">
<tr>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_front.png" alt="Front view" style="max-width:100%;"><br><em>Front</em></td>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_left.png" alt="Left view" style="max-width:100%;"><br><em>Left</em></td>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_right.png" alt="Right view" style="max-width:100%;"><br><em>Right</em></td>
</tr>
<tr>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_top.png" alt="Top view" style="max-width:100%;"><br><em>Top</em></td>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_bottom.png" alt="Bottom view" style="max-width:100%;"><br><em>Bottom</em></td>
<td style="text-align:center; padding:8px; border:none;"><img src="/images/suckless-ogl/ref_front_sony_a7siii.png" alt="Sony A7S III Profile" style="max-width:100%;"><br><em>Sony A7S III</em></td>
</tr>
</table>

---

## Full Data Flow Pipeline

<pre class="mermaid">
graph TD
    POLL("① CPU — glfwPollEvents()") --> TIME("② CPU — Δt calculation")
    TIME --> CAM("③ CPU — Camera physics 60Hz")
    CAM --> SORT("④ CPU → GPU — Sphere sorting")
    SORT --> FBO("⑤ GPU — Bind Scene FBO, Clear")
    FBO --> SKY("🌅 Skybox Pass — Equirectangular sampling")
    SKY --> SPHERES("🔮 Billboard Pass — 1 draw call, 100 instances, ray-tracing")
    SPHERES --> BLOOM("✨ Bloom + DoF + Auto-Exposure + Motion Blur")
    BLOOM --> COMP("🎬 Final Composite — 9 textures, UBO, fullscreen quad")
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

## Glossary

> Quick reference for technical terms used in this article, with links to official documentation.

### Languages, APIs & Standards

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-c11"></a>**C11** | 2011 revision of the C language standard, used for the entire engine | [cppreference — C11](https://en.cppreference.com/w/c/11) |
| <a id="glossary-opengl-44"></a>**OpenGL 4.4** | Low-level graphics API for communicating with the GPU | [OpenGL 4.4 Spec (Khronos)](https://registry.khronos.org/OpenGL/specs/gl/glspec44.core.pdf) |
| <a id="glossary-core-profile"></a>**Core Profile** | OpenGL mode that removes deprecated functions (fixed-function pipeline) | [OpenGL Wiki — Core Profile](https://www.khronos.org/opengl/wiki/OpenGL_Context#OpenGL_3.1_and_ARB_compatibility) |
| <a id="glossary-glsl"></a>**GLSL** | *OpenGL Shading Language* — the language for GPU programs (shaders) | [GLSL Spec (Khronos)](https://registry.khronos.org/OpenGL/specs/gl/GLSLangSpec.4.40.pdf) |
| <a id="glossary-glfw"></a>**GLFW** | C library for creating windows and handling keyboard/mouse input | [glfw.org](https://www.glfw.org/documentation.html) |
| <a id="glossary-glad"></a>**GLAD** | OpenGL loader generator — resolves GL function addresses at runtime | [GLAD Generator](https://glad.dav1d.de/) |
| <a id="glossary-glx"></a>**GLX** | X11 extension bridging the Window System and OpenGL on Linux | [GLX Spec (Khronos)](https://registry.khronos.org/OpenGL/specs/gl/glx1.4.pdf) |
| <a id="glossary-x11"></a>**X11** | Historic Linux windowing system (display server) | [X.Org](https://www.x.org/wiki/) |
| <a id="glossary-mesa"></a>**Mesa** | Open-source implementation of graphics APIs (OpenGL, Vulkan) on Linux | [mesa3d.org](https://www.mesa3d.org/) |

### 3D Rendering — Core Concepts

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-pbr"></a>**PBR** | *Physically-Based Rendering* — lighting model that simulates real physics of light | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-ibl"></a>**IBL** | *Image-Based Lighting* — lighting extracted from a panoramic HDR environment image | [learnopengl.com — IBL](https://learnopengl.com/PBR/IBL/Diffuse-irradiance) |
| <a id="glossary-hdr"></a>**HDR** | *High Dynamic Range* — color values exceeding 1.0 (realistic light intensities) | [learnopengl.com — HDR](https://learnopengl.com/Advanced-Lighting/HDR) |
| <a id="glossary-ldr"></a>**LDR** | *Low Dynamic Range* — color values 0–255, what the screen actually displays | [learnopengl.com — HDR](https://learnopengl.com/Advanced-Lighting/HDR) |
| <a id="glossary-shader"></a>**Shader** | Program executed directly on the GPU (vertex, fragment, compute) | [OpenGL Wiki — Shader](https://www.khronos.org/opengl/wiki/Shader) |
| <a id="glossary-vertex-shader"></a>**Vertex Shader** | Shader that processes each geometry vertex (position, projection) | [OpenGL Wiki — Vertex Shader](https://www.khronos.org/opengl/wiki/Vertex_Shader) |
| <a id="glossary-fragment-shader"></a>**Fragment Shader** | Shader that computes the color of each on-screen pixel | [OpenGL Wiki — Fragment Shader](https://www.khronos.org/opengl/wiki/Fragment_Shader) |
| <a id="glossary-compute-shader"></a>**Compute Shader** | General-purpose GPU shader outside the rendering pipeline | [OpenGL Wiki — Compute Shader](https://www.khronos.org/opengl/wiki/Compute_Shader) |
| <a id="glossary-skybox"></a>**Skybox** | Panoramic image displayed as scene background (sky/environment) | [learnopengl.com — Cubemaps](https://learnopengl.com/Advanced-OpenGL/Cubemaps) |
| <a id="glossary-rasterization"></a>**Rasterization** | Process of converting 3D triangles into 2D pixels on screen | [OpenGL Wiki — Rasterization](https://www.khronos.org/opengl/wiki/Rasterization) |
| <a id="glossary-draw-call"></a>**Draw Call** | A CPU→GPU call requesting geometry rendering | [OpenGL Wiki — Rendering Pipeline](https://www.khronos.org/opengl/wiki/Rendering_Pipeline_Overview) |
| <a id="glossary-instanced-rendering"></a>**Instanced Rendering** | Technique to draw N copies of an object in a single draw call | [OpenGL Wiki — Instancing](https://www.khronos.org/opengl/wiki/Vertex_Rendering#Instancing) |
| <a id="glossary-mipmap"></a>**Mipmap** | Pre-reduced versions of a texture (½, ¼, ⅛…) for cleaner filtering at distance | [OpenGL Wiki — Texture#Mip_maps](https://www.khronos.org/opengl/wiki/Texture#Mip_maps) |

### OpenGL GPU Objects

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-fbo"></a>**FBO** | *Framebuffer Object* — offscreen render surface (draw to it instead of the screen) | [OpenGL Wiki — Framebuffer Object](https://www.khronos.org/opengl/wiki/Framebuffer_Object) |
| <a id="glossary-mrt"></a>**MRT** | *Multiple Render Targets* — write to several textures in a single render pass | [OpenGL Wiki — MRT](https://www.khronos.org/opengl/wiki/Framebuffer_Object#Multiple_Render_Targets) |
| <a id="glossary-vao"></a>**VAO** | *Vertex Array Object* — describes the format of geometric data sent to the GPU | [OpenGL Wiki — VAO](https://www.khronos.org/opengl/wiki/Vertex_Specification#Vertex_Array_Object) |
| <a id="glossary-vbo"></a>**VBO** | *Vertex Buffer Object* — GPU buffer containing vertex positions, normals, etc. | [OpenGL Wiki — VBO](https://www.khronos.org/opengl/wiki/Vertex_Specification#Vertex_Buffer_Object) |
| <a id="glossary-ssbo"></a>**SSBO** | *Shader Storage Buffer Object* — read/write GPU buffer accessible from shaders | [OpenGL Wiki — SSBO](https://www.khronos.org/opengl/wiki/Shader_Storage_Buffer_Object) |
| <a id="glossary-ubo"></a>**UBO** | *Uniform Buffer Object* — data block shared between CPU and shaders | [OpenGL Wiki — UBO](https://www.khronos.org/opengl/wiki/Uniform_Buffer_Object) |
| <a id="glossary-pbo"></a>**PBO** | *Pixel Buffer Object* — buffer for asynchronous CPU↔GPU pixel transfers | [OpenGL Wiki — PBO](https://www.khronos.org/opengl/wiki/Pixel_Buffer_Object) |
| <a id="glossary-texture-view"></a>**Texture View** | Alternate view of an existing texture's data (different format or layers) | [OpenGL Wiki — Texture View](https://www.khronos.org/opengl/wiki/Texture_Storage#Texture_views) |

### Ray-Tracing & Geometry

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-ray-tracing"></a>**Ray-Tracing** | Technique that traces light rays to compute intersections with objects | [Scratchapixel — Ray-Sphere](https://www.scratchapixel.com/lessons/3d-basic-rendering/minimal-ray-tracer-rendering-simple-shapes/ray-sphere-intersection.html) |
| <a id="glossary-billboard"></a>**Billboard** | Screen-facing quad used here as a ray-tracing surface | [OpenGL Wiki — Billboard](https://www.khronos.org/opengl/wiki/Billboards) |
| <a id="glossary-aabb"></a>**AABB** | *Axis-Aligned Bounding Box* — axis-aligned enclosing box for fast culling | [Wikipedia — AABB](https://en.wikipedia.org/wiki/Minimum_bounding_box#Axis-aligned_minimum_bounding_box) |
| <a id="glossary-icosphere"></a>**Icosphere** | Sphere built by subdividing an icosahedron (20 faces) — more uniform than a UV sphere | [Wikipedia — Icosphere](https://en.wikipedia.org/wiki/Geodesic_polyhedron) |
| <a id="glossary-discriminant"></a>**Discriminant** | Mathematical value (b²−c) determining whether a ray hits a sphere | [Scratchapixel — Ray-Sphere](https://www.scratchapixel.com/lessons/3d-basic-rendering/minimal-ray-tracer-rendering-simple-shapes/ray-sphere-intersection.html) |
| <a id="glossary-normal"></a>**Normal** | Vector perpendicular to the surface at a point — determines surface orientation | [learnopengl.com — Basic Lighting](https://learnopengl.com/Lighting/Basic-Lighting) |
| <a id="glossary-tessellation"></a>**Tessellation** | Subdividing geometry into finer triangles for more detail | [OpenGL Wiki — Tessellation](https://www.khronos.org/opengl/wiki/Tessellation) |
| <a id="glossary-mesh"></a>**Mesh** | Collection of triangles forming a 3D object | [Wikipedia — Polygon mesh](https://en.wikipedia.org/wiki/Polygon_mesh) |
| <a id="glossary-quad"></a>**Quad** | Rectangle made of 2 triangles — the basic 2D primitive | [learnopengl.com — Hello Triangle](https://learnopengl.com/Getting-started/Hello-Triangle) |

### PBR & Lighting

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-brdf"></a>**BRDF** | *Bidirectional Reflectance Distribution Function* — describes how light bounces off a surface | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-brdf-lut"></a>**BRDF LUT** | Pre-computed texture encoding the BRDF integral for all (angle, roughness) combinations | [learnopengl.com — Specular IBL](https://learnopengl.com/PBR/IBL/Specular-IBL) |
| <a id="glossary-fresnel-schlick"></a>**Fresnel-Schlick** | Approximation of the Fresnel effect: surfaces reflect more at grazing angles | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-ggx---smith-ggx"></a>**GGX / Smith-GGX** | Microfacet model for geometry and normal distribution (roughness) | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-ndf"></a>**NDF** | *Normal Distribution Function* — statistical distribution of microfacet orientations | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-albedo"></a>**Albedo** | Base color of a material (without lighting) | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-metallic"></a>**Metallic** | PBR parameter: 0 = dielectric (plastic, wood), 1 = metal (gold, chrome) | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-roughness"></a>**Roughness** | PBR parameter: 0 = perfect mirror, 1 = completely matte | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-ao"></a>**AO** | *Ambient Occlusion* — darkens crevices and corners (ambient light occlusion) | [learnopengl.com — SSAO](https://learnopengl.com/Advanced-Lighting/SSAO) |
| <a id="glossary-dielectric"></a>**Dielectric** | Non-metallic material (plastic, glass, wood) — reflects little at direct angles | [learnopengl.com — PBR Theory](https://learnopengl.com/PBR/Theory) |
| <a id="glossary-irradiance-map"></a>**Irradiance Map** | Texture encoding hemisphere-integrated diffuse ambient light for each direction | [learnopengl.com — Diffuse Irradiance](https://learnopengl.com/PBR/IBL/Diffuse-irradiance) |
| <a id="glossary-specular-prefilter"></a>**Specular Prefilter** | Mip-mapped texture encoding blurred reflections by roughness level | [learnopengl.com — Specular IBL](https://learnopengl.com/PBR/IBL/Specular-IBL) |
| <a id="glossary-equirectangular"></a>**Equirectangular** | 2D projection of a sphere (like a world map) — the format of `.hdr` images | [Wikipedia — Equirectangular](https://en.wikipedia.org/wiki/Equirectangular_projection) |
| <a id="glossary-sh-probes"></a>**SH Probes** | *Spherical Harmonics* — compact representation of a low-frequency light field | [Wikipedia — SH Lighting](https://en.wikipedia.org/wiki/Spherical_harmonic_lighting) |

### Post-Processing

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-bloom"></a>**Bloom** | Glow halo around very bright areas (lens light diffusion) | [learnopengl.com — Bloom](https://learnopengl.com/Advanced-Lighting/Bloom) |
| <a id="glossary-depth-of-field-dof"></a>**Depth of Field (DoF)** | Blur of objects outside the focus distance | [Wikipedia — Depth of field](https://en.wikipedia.org/wiki/Depth_of_field) |
| <a id="glossary-coc"></a>**CoC** | *Circle of Confusion* — blur disc diameter for an out-of-focus point | [Wikipedia — CoC](https://en.wikipedia.org/wiki/Circle_of_confusion) |
| <a id="glossary-bokeh"></a>**Bokeh** | Aesthetic shape of background blur (discs, hexagons…) | [Wikipedia — Bokeh](https://en.wikipedia.org/wiki/Bokeh) |
| <a id="glossary-motion-blur"></a>**Motion Blur** | Per-pixel motion blur simulating a camera shutter | [GPU Gems — Motion Blur](https://developer.nvidia.com/gpugems/gpugems3/part-iv-image-effects/chapter-27-motion-blur-post-processing-effect) |
| <a id="glossary-fxaa"></a>**FXAA** | *Fast Approximate Anti-Aliasing* — fast post-process anti-aliasing on the final image | [NVIDIA — FXAA](https://developer.download.nvidia.com/assets/gamedev/files/sdk/11/FXAA_WhitePaper.pdf) |
| <a id="glossary-msaa"></a>**MSAA** | *Multisample Anti-Aliasing* — geometric anti-aliasing (expensive, avoided here) | [OpenGL Wiki — Multisampling](https://www.khronos.org/opengl/wiki/Multisampling) |
| <a id="glossary-tonemapping"></a>**Tonemapping** | Conversion of HDR colors (unbounded) to displayable LDR (0–255) | [learnopengl.com — HDR](https://learnopengl.com/Advanced-Lighting/HDR) |
| <a id="glossary-color-grading"></a>**Color Grading** | Creative color adjustments (saturation, contrast, gamma, hue) | [Wikipedia — Color grading](https://en.wikipedia.org/wiki/Color_grading) |
| <a id="glossary-3d-lut"></a>**3D LUT** | 3D color lookup table for a cinematic "look" (`.cube` file) | [Wikipedia — 3D LUT](https://en.wikipedia.org/wiki/3D_lookup_table) |
| <a id="glossary-vignette"></a>**Vignette** | Progressive darkening of image edges (lens effect) | [Wikipedia — Vignetting](https://en.wikipedia.org/wiki/Vignetting) |
| <a id="glossary-dithering"></a>**Dithering** | Adding imperceptible noise to break banding artifacts in gradients | [Wikipedia — Dither](https://en.wikipedia.org/wiki/Dither) |
| <a id="glossary-auto-exposure"></a>**Auto-Exposure** | Automatic scene brightness adaptation (simulates the eye's iris) | [learnopengl.com — HDR](https://learnopengl.com/Advanced-Lighting/HDR) |
| <a id="glossary-vsync"></a>**VSync** | *Vertical Sync* — syncs rendering with screen refresh (prevents tearing) | [Wikipedia — VSync](https://en.wikipedia.org/wiki/Screen_tearing#V-sync) |

### Architecture & Performance

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-simd"></a>**SIMD** | *Single Instruction, Multiple Data* — vector computation (1 instruction processes 4+ values) | [Wikipedia — SIMD](https://en.wikipedia.org/wiki/Single_instruction,_multiple_data) |
| <a id="glossary-sse"></a>**SSE** | Intel/AMD SIMD extensions for x86 (128-bit registers) | [Intel — SSE Intrinsics](https://www.intel.com/content/www/us/en/docs/intrinsics-guide/index.html) |
| <a id="glossary-neon"></a>**NEON** | ARM SIMD extensions (smartphones, Apple Silicon, Raspberry Pi) | [ARM — NEON](https://developer.arm.com/Architectures/Neon) |
| <a id="glossary-vram"></a>**VRAM** | Dedicated GPU memory — where textures and buffers reside | [Wikipedia — VRAM](https://en.wikipedia.org/wiki/Video_RAM_(dual-ported_DRAM)) |
| <a id="glossary-dma"></a>**DMA** | *Direct Memory Access* — data transfer without CPU involvement | [Wikipedia — DMA](https://en.wikipedia.org/wiki/Direct_memory_access) |
| <a id="glossary-cache-friendly"></a>**Cache-friendly** | Memory layout that minimizes CPU cache misses (contiguous data) | [Wikipedia — Cache](https://en.wikipedia.org/wiki/CPU_cache#Cache-friendly_code) |
| <a id="glossary-lru-cache"></a>**LRU Cache** | *Least Recently Used* — cache that evicts the least recently used entry | [Wikipedia — LRU](https://en.wikipedia.org/wiki/Cache_replacement_policies#Least_recently_used_(LRU)) |
| <a id="glossary-fence-glsync"></a>**Fence (GLSync)** | GPU sync object — lets you wait for GPU work to complete | [OpenGL Wiki — Sync Object](https://www.khronos.org/opengl/wiki/Sync_Object) |
| <a id="glossary-memory-barrier"></a>**Memory Barrier** | GPU instruction ensuring previous writes are visible before subsequent reads | [OpenGL Wiki — Memory Barrier](https://www.khronos.org/opengl/wiki/Memory_Model#Explicit_memory_barriers) |
| <a id="glossary-work-group"></a>**Work Group** | Group of GPU threads executed together in a compute shader (e.g. 16×16 = 256 threads) | [OpenGL Wiki — Compute Shader](https://www.khronos.org/opengl/wiki/Compute_Shader#Compute_space) |
| <a id="glossary-dispatch"></a>**Dispatch** | CPU call that launches a compute shader on the GPU | [OpenGL Wiki — Compute Shader](https://www.khronos.org/opengl/wiki/Compute_Shader#Dispatch) |

### Mathematics & Camera

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-mat4---vec3"></a>**mat4 / vec3** | 4×4 matrix and 3D vector — fundamental 3D types | [cglm docs](https://cglm.readthedocs.io/en/latest/) |
| <a id="glossary-fov"></a>**FOV** | *Field of View* — camera viewing angle (60° here) | [Wikipedia — FOV](https://en.wikipedia.org/wiki/Field_of_view) |
| <a id="glossary-view-matrix"></a>**View Matrix** | Transforms world coordinates into camera coordinates (`lookAt`) | [learnopengl.com — Camera](https://learnopengl.com/Getting-started/Camera) |
| <a id="glossary-projection-matrix"></a>**Projection Matrix** | Transforms 3D to 2D with perspective (far objects = smaller) | [learnopengl.com — Coordinate Systems](https://learnopengl.com/Getting-started/Coordinate-Systems) |
| <a id="glossary-yaw---pitch"></a>**Yaw / Pitch** | Yaw = left-right rotation, Pitch = up-down rotation of the camera | [learnopengl.com — Camera](https://learnopengl.com/Getting-started/Camera) |
| <a id="glossary-lerp"></a>**Lerp** | *Linear Interpolation* — smooth transition between two values: `a + t × (b − a)` | [Wikipedia — Lerp](https://en.wikipedia.org/wiki/Linear_interpolation) |
| <a id="glossary-ema"></a>**EMA** | *Exponential Moving Average* — weighted average favoring recent values | [Wikipedia — EMA](https://en.wikipedia.org/wiki/Exponential_smoothing) |
| <a id="glossary-smoothstep"></a>**Smoothstep** | S-curve interpolation function (smooth transition between 0 and 1) | [Khronos — smoothstep](https://registry.khronos.org/OpenGL-Refpages/gl4/html/smoothstep.xhtml) |
| <a id="glossary-z-buffer---depth-buffer"></a>**Z-buffer / Depth Buffer** | Texture storing per-pixel depth to handle occlusion | [learnopengl.com — Depth Testing](https://learnopengl.com/Advanced-OpenGL/Depth-testing) |
| <a id="glossary-stencil-buffer"></a>**Stencil Buffer** | Per-pixel mask restricting rendering to specific areas | [learnopengl.com — Stencil](https://learnopengl.com/Advanced-OpenGL/Stencil-testing) |

### Sorting Algorithms

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-bitonic-sort"></a>**Bitonic Sort** | Parallel sort suited for GPUs — compares and swaps in pairs | [Wikipedia — Bitonic sort](https://en.wikipedia.org/wiki/Bitonic_sorter) |
| <a id="glossary-radix-sort"></a>**Radix Sort** | Sort by successive digits — O(n·k), efficient on CPU for integer keys | [Wikipedia — Radix sort](https://en.wikipedia.org/wiki/Radix_sort) |
| <a id="glossary-back-to-front"></a>**Back-to-front** | Rendering order from farthest to nearest, required for correct transparency | [Wikipedia — Painter's algorithm](https://en.wikipedia.org/wiki/Painter%27s_algorithm) |

### Multithreading

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-posix-threads"></a>**POSIX Threads** | Standard threading API on Unix/Linux (`pthread_create`, `pthread_cond_wait`) | [man — pthreads](https://man7.org/linux/man-pages/man7/pthreads.7.html) |
| <a id="glossary-async-loading"></a>**Async Loading** | Running disk I/O on a separate thread to avoid blocking the render loop | [Wikipedia — Async I/O](https://en.wikipedia.org/wiki/Asynchronous_I/O) |
| <a id="glossary-condition-variable"></a>**Condition Variable** | Sync mechanism: a thread sleeps until another signals it | [man — pthread_cond_wait](https://man7.org/linux/man-pages/man3/pthread_cond_wait.3p.html) |

### Miscellaneous

| Term | Description | Link |
|------|------------|------|
| <a id="glossary-tracy"></a>**Tracy** | Real-time profiler for games and graphics apps (per-frame CPU + GPU measurement) | [Tracy Profiler (GitHub)](https://github.com/wolfpld/tracy) |
| <a id="glossary-cglm"></a>**cglm** | SIMD-optimized C math library for 3D (matrices, vectors, quaternions) | [cglm (GitHub)](https://github.com/recp/cglm) |
| <a id="glossary-stbimage"></a>**stb_image** | Single-header C library for loading images (PNG, JPEG, HDR…) | [stb (GitHub)](https://github.com/nothings/stb) |
| <a id="glossary-fixed-timestep"></a>**Fixed Timestep** | Physics update at a constant interval (e.g. 60 Hz) regardless of framerate | [Fix Your Timestep! (Fiedler)](https://gafferongames.com/post/fix_your_timestep/) |
| <a id="glossary-game-loop"></a>**Game Loop** | Main application loop: read input → update → render → repeat | [Game Programming Patterns — Game Loop](https://gameprogrammingpatterns.com/game-loop.html) |
| <a id="glossary-fireflies"></a>**Fireflies** | Ultra-bright aberrant pixels caused by extreme HDR values (artifact) | [Physically Based — Fireflies](https://pbr-book.org/4ed/Sampling_and_Reconstruction/Filtering_Image_Samples#FireflyPrevention) |
| <a id="glossary-premultiplied-alpha"></a>**Premultiplied Alpha** | Convention where RGB is already multiplied by alpha — enables correct blending | [Wikipedia — Premultiplied alpha](https://en.wikipedia.org/wiki/Alpha_compositing#Straight_versus_premultiplied) |

---

## Conclusion

**suckless-ogl** demonstrates that a complete PBR engine can be built with readable C11 code, a clear rendering pipeline, and GPU performance measured in milliseconds. The design choices — billboard ray-tracing instead of meshes, async HDR loading, progressive IBL, modular post-processing — show how to solve real graphics problems with elegance.

The full source code is available on [GitHub](https://github.com/yoyonel/suckless-ogl), and the detailed technical documentation at [yoyonel.github.io/suckless-ogl](https://yoyonel.github.io/suckless-ogl/).

*In upcoming articles, we'll explore the Vulkan and NVRHI projects that push these concepts even further.*
