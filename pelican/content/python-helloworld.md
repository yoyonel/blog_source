---
title: "Hello World" en Python
date: 2020-01-06
description: Exemple Python pour afficher "Hello World!"
tags: Python
category: Développement
CSS: asciinema-player.css
JS: asciinema-player.js (top)
---

# Comment afficher "Hello World!" en Python

## Code source
```python
def helloworld():
    print("Hello World!")

if __name__ == '__main__':
    helloworld()
```

## Résultats

```shell
╰─ echo "def helloworld():\n\tprint('Hello World!')\n\nif __name__ == '__main__':\n\thelloworld()" | python
Hello World!
```
<asciinema-player src="{static}/python-helloworld-ascii.cast" rows=10 poster="npt:0:10" title="Shell record de l'exécution d'un HelloWorld en Python" author="Bloggy" author-img-url=https://cdn.fbsbx.com/v/t59.2708-21/54258800_595054434302598_3189230714423869440_n.gif?_nc_cat=109&_nc_ohc=KQZcBpE9TsMAX9qb-Uh&_nc_ht=cdn.fbsbx.com&oh=4f4cd59722decd795b5be98137602c4f&oe=5E174CC2></asciinema-player>