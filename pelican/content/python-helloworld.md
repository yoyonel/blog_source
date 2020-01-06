---
title: "Hello World" en Python
date: 2020-01-06
description: Exemple Python pour afficher "Hello World!"
tags: Python

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
