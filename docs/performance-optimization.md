# Optimisation des performances de chargement

> Date : 2026-03-31
> Branche : `perf/optimize-page-load`
> Page de test : `suckless-ogl-anatomie-frame.html` (~10-15s → ~2-3s)

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

### 4. Images — lazy loading automatique

**Fichier** : `plugins/lazy_images.py` (nouveau plugin)

Plugin Pelican qui ajoute `loading="lazy"` à toutes les balises `<img>` du HTML
généré qui n'ont pas déjà un attribut `loading`.

```python
# Regex qui matche les <img> sans attribut loading
_IMG_RE = re.compile(r"<img\b(?![^>]*\bloading\s*=)", re.IGNORECASE)
```

Activé dans `pelicanconf.py` :

```python
PLUGINS = ["css_js_injector", "lazy_images", "i18n_subsites"]
```

## Résumé des fichiers modifiés

| Fichier | Type de modification |
|---------|---------------------|
| `pelicanconf.py` | Ajout plugin `lazy_images`, commentaire Disqus |
| `publishconf.py` | Commenté `GOOGLE_ANALYTICS`, réactivé `DISQUS_SITENAME` |
| `themes/Flex/templates/partial/disqus.html` | IntersectionObserver lazy-load |
| `plugins/lazy_images.py` | **Nouveau** — plugin lazy loading images |
| `content/suckless-ogl-anatomie-frame.md` | Refs images → `.webp` |
| `content/suckless-ogl-anatomie-frame-en.md` | Refs images → `.webp` |
| `content/images/suckless-ogl/*.webp` | **Nouveau** — 22 images WebP |

## Vérification

Après `just build`, vérifier dans le HTML généré :

```bash
# 22 images avec lazy loading
grep -c 'loading="lazy"' output/suckless-ogl-anatomie-frame.html

# 21 refs WebP, 0 PNG/JPG
grep -c '\.webp' output/suckless-ogl-anatomie-frame.html
grep -c 'suckless-ogl.*\.png\|suckless-ogl.*\.jpg' output/suckless-ogl-anatomie-frame.html

# Disqus lazy-loaded
grep 'IntersectionObserver' output/suckless-ogl-anatomie-frame.html

# Pas de Google Analytics
grep -c 'google-analytics\|GoogleAnalyticsObject' output/suckless-ogl-anatomie-frame.html
```

## Améliorations futures possibles

- Supprimer les fichiers PNG/JPG originaux du repo (économiser ~14 Mo dans git)
- Remplacer Disqus par [giscus](https://giscus.app/) (GitHub Discussions, sans tracker)
- Ajouter `<link rel="preconnect">` pour Google Fonts
- Mettre en place un analytics léger (Plausible / Cloudflare Web Analytics)
