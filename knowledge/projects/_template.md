---
title: Nome do Projeto
date: YYYY-MM-DD
tags: [project]
type: project
status: active
aliases: []
---

# Nome do Projeto

Descrição breve.

## Estado Atual

### Frente X
Estado, bloqueios, próximos passos.

## Links

- [[doc|título]]

## Notas Relacionadas

```dataview
TABLE date, tags, title
FROM "knowledge"
WHERE context = "slug" OR contains(tags, "slug")
SORT date DESC
```
