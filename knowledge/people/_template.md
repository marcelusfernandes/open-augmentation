---
type: person
name: "Nome Completo"
slug: nome-slug
aliases: [Apelido 1, Apelido 2]
org: work                        # work | external | personal
team:             # opcional, kebab-case (ex: eng, dados, design, ...)
role: "Descrição curta do papel"
status: active                   # active | paused | left | external
projects: [slug-projeto]         # slugs de projetos onde aparece
context: work
tags: [person]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Nome Completo

Descrição curta de 1-2 frases sobre quem é a pessoa, time, foco.

## Como reconhecer
- Como aparece em transcrições, apelidos, contextos típicos.

## Padrão observado (opcional)
- Comportamentos recorrentes que vale lembrar pra próximas interações.

## Quando não confundir (opcional)
- Diferenciar de outras pessoas com nome parecido (ex: dois "Bruno" no time, ou um xará interno vs. externo).

<!--
Convenções:
- `aliases:` lista TODAS as formas que a pessoa aparece em arquivos antigos (incluindo nome com sobrenome diferente, primeiro nome só, etc.)
- `org`: work (colegas internos / time), external (parceiros, fornecedores, consultores), personal (mentoria, network pessoal — não cruza com projetos do trabalho)
- `status: external` é pra contatos pontuais que não fazem parte do dia a dia
- Body curto e cirúrgico (~30 linhas tipico). Stubs (liderados com ficha rica em outro lugar) ainda menores.
- NÃO criar wikilink `[[nome-slug]]` no body de outras notas. Pessoas continuam metadata em `people:` do frontmatter — `people/` é diretório de lookup/desambiguação, não entity hub do graph.
-->
