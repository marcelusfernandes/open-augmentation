---
description: Status executivo da última semana ISO (seg-dom) de um projeto, salvo na pasta weekly-status/
argument-hint: <project-slug>
---

Gera um **status executivo da última semana ISO completa (seg-dom)** para o projeto `$ARGUMENTS`, salvando em `knowledge/projects/$ARGUMENTS/weekly-status/<domingo-da-janela>.md`.

O objetivo é destilar a semana em um documento que sirva pra alinhar com liderança/stakeholders — não é resumo cronológico, é leitura executiva do **estado atual**.

---

## 1. Validar projeto e preparar pasta

```bash
PROJECT_DIR="knowledge/projects/$ARGUMENTS"
[ -d "$PROJECT_DIR" ] || { echo "Projeto não encontrado: $ARGUMENTS"; exit 1; }
mkdir -p "$PROJECT_DIR/weekly-status"
```

Se o slug não bater (ex: usuário escreveu "Projeto Alfa" em vez de `projeto-alfa`), tente `qmd query "lex:$ARGUMENTS"` filtrado em `projects/` pra sugerir o slug correto antes de abortar.

## 2. Definir janela ISO e arquivo de saída

**Convenção oficial:** semana ISO segunda-a-domingo. Nome do arquivo = domingo da janela.

Calcular a **última semana completa** (a que terminou no domingo mais recente):

```bash
# Dia da semana ISO (1=Mon, 7=Sun)
DOW=$(date +%u)

# Dias até o domingo mais recente que JÁ TERMINOU
if [ "$DOW" = "7" ]; then
  DAYS_TO_LAST_SUN=7   # se hoje é domingo, fechar a semana anterior
else
  DAYS_TO_LAST_SUN=$DOW
fi

WEEK_END=$(date -v-${DAYS_TO_LAST_SUN}d +%Y-%m-%d)         # domingo (fim)
WEEK_START=$(date -v-$((DAYS_TO_LAST_SUN+6))d +%Y-%m-%d)   # segunda (início)
WEEK_NUM=$(date -v-${DAYS_TO_LAST_SUN}d +%V)               # semana ISO (W##)
WEEK_YEAR=$(date -v-${DAYS_TO_LAST_SUN}d +%G)              # ano ISO

OUTPUT_FILE="$PROJECT_DIR/weekly-status/${WEEK_END}.md"
```

**Edge cases:**
- Se hoje é segunda, a janela é a semana que terminou ontem (domingo).
- Se hoje é domingo, fechar a semana ISO anterior (não a corrente).
- Se já existe arquivo do mesmo domingo, perguntar antes de sobrescrever.

**Variante "semana corrente":** se usuário pedir explicitamente status da semana em curso (`--current` ou nas instruções), usar a segunda atual até hoje. Avisar que é parcial.

## 3. Coletar dados (paralelo onde fizer sentido)

1. **Log do projeto** — fonte primária. Ler `$PROJECT_DIR/log/$(date -v-${DAYS_TO_LAST_SUN}d +%Y-%m).md`. Se a janela cruza mês (ex: 27/04 a 03/05), ler também o mês anterior. **Filtrar APENAS entradas datadas entre `$WEEK_START` e `$WEEK_END` inclusive.**

2. **MOC do projeto** — `$PROJECT_DIR/$ARGUMENTS.md` (ou `identity.md`/`meta-catalog.md` se existirem). Lê o estado declarado pra entender as frentes ativas — mas filtra: nem toda frente do MOC estava ativa na semana.

3. **Status anterior** — listar `$PROJECT_DIR/weekly-status/*.md` ordenados; ler o mais recente pra capturar o delta. Wikilink dele vai pra seção "Relacionados" como `[[YYYY-MM-DD|← Semana anterior (DD/MM-DD/MM)]]`.

4. **Reuniões e notas relacionadas** — `qmd query "lex:$ARGUMENTS"` filtrado pela janela, focando `meetings/` e `notes/`. Olhar também frontmatter `context: $ARGUMENTS` ou `tags: [$ARGUMENTS]`.

5. **Journal** — `qmd multi-get "journal/${WEEK_START_YYYYMM}-*.md"` filtrado pra entradas da janela mencionando o projeto.

6. **active-contexts** — `memory/active-contexts.md` pra saber o que tá declarado como estado/bloqueio atual.

## 4. Sintetizar (não copiar, não inventar)

Status executivo é destilação. Regras críticas:

- **Não invente.** Se uma frente do MOC não aparece no log da janela, **omita**. Status enxuto é fiel.
- **Delta-first:** se há status anterior, comece pelo que mudou em relação a ele.
- **Frentes como unidade de organização** — pra cada frente ativa: estado, quem puxa, bloqueio, próximo passo. Status em CAPS no header (DESTRAVADO / TRAVADO / EM CURSO / EM RISCO / DECISÃO TOMADA / etc.).
- **Nomes próprios importam** — preserve quem aprovou, quem tá travando, quem tá puxando.
- **Datas absolutas** — converter "semana que vem" → "semana de DD/MM".
- **Sem narrar reunião por reunião** — extrair decisões e estado, descartar discussão.
- **Riscos explícitos** — se algo pode dar errado, fala, com transparência.
- **Próximos marcos com data** — tabela curta, com dono.

**Tamanho alvo:** 1000-1800 palavras. Briefing pra quem tem 2 minutos, não dissertação.

## 5. Formato de saída

```markdown
---
title: <Nome do Projeto> — Status Semanal <DD/MM-DD/MM>
date: <WEEK_END YYYY-MM-DD>
tags: [<project-slug>, status, weekly-status]
people: [<nome-do-usuario>]
context: <project-slug>
type: weekly-status
week: <WEEK_YEAR>-W<WEEK_NUM>
---

# <Nome do Projeto> — Status Semanal <DD/MM-DD/MM/YYYY>

**Janela:** <DD/MM> (seg) a <DD/MM> (dom) — Semana ISO <NN>.
**Status geral:** <1 linha — 🟢 on-track / 🟡 com risco / 🔴 bloqueado / 🚀 destravado>

## TL;DR

<2-4 frases. O que importa essa semana, sem rodeios.>

---

## Frentes

### 1. <Nome da Frente> — <STATUS EM CAPS>
<Estado em 1-3 frases. Quem tá puxando. Bloqueio se houver. Próximo passo concreto.>

### 2. <Nome da Frente> — <STATUS>
...

---

## Decisões da Semana

- <decisão + por quê, em 1 linha>

## Riscos & Pendências

| Risco / Pendência | Impacto | Dono |
|---|---|---|
| ... | ... | ... |

## Próximos Marcos

| Quando | O quê | Dono |
|---|---|---|
| <DD/MM> | <marco> | <pessoa> |

---

## Relacionados
- [[<project-slug>|<Nome do Projeto> — MOC]]
- [[<YYYY-MM-DD>|← Semana anterior (DD/MM-DD/MM)]]   <!-- se existir -->
- [[log/<YYYY-MM>|Log <Mês> <YYYY>]]
- <wikilinks pras reuniões/notas mais relevantes da semana>
```

**Tom:** executivo, direto, sem rodeio. Não é journal — é briefing.

## 6. Pós-escrita

1. **Atualizar MOC** se algo do estado atual ficou desatualizado em relação à semana — sugerir o diff ao usuário antes de aplicar.
2. **Atualizar `memory/active-contexts.md`** se o status do projeto mudou (destravou / entrou em risco / mudou prioridade).
3. **Indexar:** `qmd update && qmd embed` (permissão já configurada).
4. **Devolver ao usuário:** caminho do arquivo + 3-bullet resumo do que entrou + qualquer divergência detectada (ex: datas conflitantes entre log e active-contexts).
