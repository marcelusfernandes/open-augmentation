---
name: obsidian-graph
description: Convenções para manter o knowledge graph do Obsidian consistente — projetos como hubs, tags como pontes, pessoas como metadata.
---

# Obsidian Knowledge Graph — Convenções

Regras para manter o graph view funcional e consistente ao criar/editar arquivos em `knowledge/`.

## Princípio

O graph mostra **projetos como hubs** e **tags de conceito como pontes cross-project**.
Pessoas são metadata canônica (frontmatter `people:`) — invisíveis no graph mesmo com fichas em `knowledge/people/` (fichas servem pra lookup/desambiguação, não viram entity hubs).

O Obsidian graph cria edges com:
- `[[wikilinks]]` — conectam documentos entre si
- `#tags` inline — conectam conceitos entre projetos

Frontmatter YAML **não** cria edges — mas é essencial para Dataview e QMD.

---

## Estrutura de Projetos

Projetos vivem em `knowledge/projects/` e evoluem organicamente:

```
# Estágio 1 — projeto novo
knowledge/projects/novo-projeto.md

# Estágio 2 — acumulou 3+ notas
knowledge/projects/novo-projeto/
  novo-projeto.md              ← MOC + estado atual
  frente-a.md                  ← frente/iniciativa

# Estágio 3 — frente cresceu
knowledge/projects/novo-projeto/
  novo-projeto.md
  frente-a/
    frente-a.md                ← MOC da frente
    detalhe-1.md
  frente-b.md
  log/
    2026-03.md                 ← log mensal
```

### Regras de promoção (eu decido sozinho)

| Situação | Ação |
|----------|------|
| Projeto novo, primeira menção | Cria `projects/nome.md` flat |
| Projeto acumulou 3+ docs | Cria pasta, move `.md` para dentro |
| Frente/iniciativa distinta identificada | Cria `.md` na pasta do projeto |
| Frente acumulou 3+ docs | Promove a subpasta |
| Nota cruza projetos ou sem projeto claro | Fica em `notes/`, conecta via wikilink |
| Info rápida, contexto solto | `notes/`, sempre |

### MOC de projeto = arquivo único

O arquivo `nome-do-projeto.md` na raiz da pasta do projeto contém:
- Descrição breve
- **Estado atual** de cada frente (reescrito a cada atualização)
- Links para frentes, meetings, status, log
- Dataview query automática

```yaml
---
title: Nome do Projeto
date: YYYY-MM-DD
tags: [project, slug]
type: project
status: active | paused | completed
aliases: []
---
```

### Log mensal

Cada projeto com pasta ganha `log/YYYY-MM.md` — destilação mensal do que aconteceu. Uma linha por evento relevante, com data. Nunca apago, nunca edito entradas passadas.

---

## Naming

### Arquivos
- **kebab-case**, lowercase, sem acentos
- Projetos: `knowledge/projects/<nome>/` ou `knowledge/projects/<nome>.md`
- Notas: `knowledge/notes/`, `knowledge/meetings/`, `knowledge/journal/` (flat)

### Frontmatter `people:`
- Array de texto com nomes canônicos
- Ex: `people: [Ana Silva, Bruno Costa]`

### Frontmatter `context:`
- Sempre **kebab-case**: `nome-do-contexto`

---

## Wikilinks

### Formato
```markdown
[[kebab-slug|Display Name]]
```

### Onde colocar
- **Seção `## Relacionados`**: ao final de toda nota, lista wikilinks para **projetos** mencionados
- **Dentro de MOCs**: links para frentes, meetings, status notes
- **Nunca** substituir frontmatter por wikilinks — frontmatter é para Dataview/QMD
- **Nunca** criar wikilinks para pessoas — pessoas ficam só no frontmatter

### Exemplo
```markdown
## Relacionados

- [[projeto-alfa|Projeto Alfa]]
- [[projeto-beta|Projeto Beta]]
```

---

## Tags: Tipo vs Conceito

### Tags de tipo (só no frontmatter YAML)
Para classificação e queries Dataview. Não precisam estar no body.
- `project`, `meeting`, `decision`, `research`, `learning`, `journal`, `log`, `initiative`

### Tags de conceito (inline no body)
Criam **pontes cross-project** no graph. Colocar no trecho específico onde a conexão existe.
- `#arquitetura-busca`, `#graph-api`, `#governanca-ai`, `#gestao-portfolio-ai`
- Adicionar quando um trecho de um projeto tem relação com outro projeto/tema
- Crescem organicamente — não inventar, só registrar conexões reais

---

## Pessoas

**Pessoas continuam metadata canônica em `people:` do frontmatter de cada nota.** Mas existe uma camada de lookup/desambiguação em `knowledge/people/` — fichas individuais por pessoa que **NÃO viram entity hubs no graph**.

### Regra dupla

1. **Frontmatter `people:` em cada nota** — fonte canônica de associação. Sempre nome completo (ex: `[Ana Silva, Bruno Costa]`).
2. **Diretório `knowledge/people/`** — fichas individuais com slug, aliases, role, projetos. Estrutura:
   ```
   knowledge/people/
     _template.md
     work/<slug>.md           # internos / time
     external/<slug>.md       # parceiros, fornecedores, consultores
     personal/<slug>.md       # mentoria, network pessoal (não cruza com trabalho)
   ```

### Regras críticas

- **NÃO criar wikilink `[[ana-silva]]` no body de outras notas.** Wikilinks no body continuam reservados a **projetos**.
- **Pessoas não viram nodes no graph** — fichas em `people/` aparecem como cluster isolado ligado só via Dataview.
- **Aliases no frontmatter da ficha** capturam todas as formas que a pessoa apareceu em arquivos antigos (ex: "Ana" → ficha `ana-silva.md`). QMD lex resolve.
- Nome canônico no frontmatter `people:` das notas usa o `name:` da ficha (não os aliases).
- Liderados diretos (gestão profunda) podem ter ficha rica em `projects/gestao-time/liderados/<slug>.md` e stub leve em `people/<org>/<slug>.md` apontando pra lá via `see_also:`.

### Quando criar ficha

- **Speaker matching pós-gravação:** se a pessoa apareceu em transcrição e não tem ficha, criar com 3 perguntas mínimas (sobrenome, org, role em 1 linha).
- **Ambiguidade:** quando 2+ pessoas com o mesmo primeiro nome confundem (ex: três Brunos), criar fichas pra cada e desambiguar em "Quando não confundir".
- **NÃO criar fichas vazias upfront** — fichas nascem por demanda real.

---

## Checklist de Validação

Ao criar/editar arquivos em `knowledge/`:

- [ ] `context:` é kebab-case
- [ ] `people:` usa nomes canônicos
- [ ] Seção `## Relacionados` existe com wikilinks para projetos
- [ ] Wikilinks usam formato `[[slug|Display Name]]`
- [ ] Tags de conceito inline onde há conexão cross-project
- [ ] Projeto com 3+ notas já tem pasta própria

---

## QMD

- Wikilinks e tags inline não quebram QMD
- **Após qualquer mudança** em `knowledge/`: rodar `qmd update && qmd embed`

---

## Obsidian Config

### Plugins
- **Dataview** (essencial) — queries nos MOCs
- **Strange New Worlds** (recomendado) — contagem de backlinks inline

### Graph View
- Filters > Tags = ON
- Groups: `path:knowledge/projects` com cor destacada
