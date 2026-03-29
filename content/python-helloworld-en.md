---
title: Python "Hello World"
slug: python-helloworld
lang: en
date: 2020-01-06
description: Python example to display "Hello World!"
tags: Python
category: Development
CSS: asciinema-player.css
JS: asciinema-player.js (top)
---

# How to print "Hello World!" in Python

## Source code
```python
def helloworld():
    print("Hello World!")

if __name__ == '__main__':
    helloworld()
```

## Output

```shell
╰─ echo "def helloworld():\n\tprint('Hello World!')\n\nif __name__ == '__main__':\n\thelloworld()" | python
Hello World!
```
<asciinema-player src="{static}/python-helloworld-ascii.cast" rows=10 poster="npt:0:10" title="Shell recording of a Python HelloWorld execution" author="Bloggy" author-img-url=https://cdn.fbsbx.com/v/t59.2708-21/54258800_595054434302598_3189230714423869440_n.gif?_nc_cat=109&_nc_ohc=KQZcBpE9TsMAX9qb-Uh&_nc_ht=cdn.fbsbx.com&oh=4f4cd59722decd795b5be98137602c4f&oe=5E174CC2></asciinema-player>
