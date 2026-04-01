# Optimisation de Performance — Conversion WebP des Images

> Date : 2026-04-01
> Auteur : Antigravity (IA Coding Assistant)
> PR associée : [#9](https://github.com/yoyonel/blog_source/pull/9)
> Branche : `perf/webp-images`

## Objectif

Réduire drastiquement le temps de chargement de l'article "Anatomie d'une frame" (et du blog en général) en s'attaquant au **Largest Contentful Paint (LCP)**, qui était de **8.45s** en raison d'images PNG/JPG non compressées et massives.

## Résultats Lighthouse (Médiane de 3 runs)

| Métrique | Avant (PNG/JPG) | Après (WebP) | Gain | Statut |
| :--- | :---: | :---: | :---: | :---: |
| **LCP** | 8.45s | **2.27s** | **-73%** | 🟢 |
| **FCP** | - | 1.05s | - | 🟢 |
| **Speed Index** | - | 1.46s | - | 🟢 |
| **TBT** | - | 291ms | - | 🟠 |
| **Score Performance** | - | **73** | - | 🟠 |

### Observations clés :
- L'optimisation WebP a permis de passer sous la barre critique des 2.5s pour le LCP.
- Le poids total des images a été réduit de **~90%** en moyenne (ex: `reference_image.webp` à 97 KB vs PNG original).
- Le score global (73) est désormais limité par le **Total Blocking Time (TBT)**, qui nécessite une optimisation séparée du JavaScript (Mermaid.js).

## Démarche Technique

1. **Conversion Batch** : Toutes les images PNG et JPG du répertoire `content/images/suckless-ogl/` ont été converties au format WebP.
2. **Nettoyage** : Les anciens fichiers sources (PNG/JPG) ont été supprimés pour alléger le dépôt Git.
3. **Mise à jour du contenu** : Les fichiers Markdown (`content/suckless-ogl-anatomie-frame.md` et sa version EN) ont été mis à jour pour pointer vers les nouvelles extensions `.webp`.
4. **Validation CI** : Les résultats Lighthouse ont été validés via le workflow automatique sur GitHub Actions.

## Prochaines étapes (Optimisation Future)

Pour atteindre un score de performance **> 90**, les pistes suivantes sont identifiées :
- **Optimisation TBT** : Lazy-loading de Mermaid.js via `IntersectionObserver` pour éviter l'exécution au chargement initial.
- **Priorité LCP** : Ajouter `fetchpriority="high"` sur l'image de héros (`reference_image.webp`).
- **Lazy-loading natif** : Ajouter `loading="lazy"` sur toutes les images sous la ligne de flottaison.

---
*Document créé pour assurer le suivi des efforts de performance du blog.*
