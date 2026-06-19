# Augmentation — Manual Operacional

## Session Startup

Antes de qualquer coisa:

1. Leia `.claude/rules/SOUL.md` — é quem você é
2. Leia `memory/user-profile.md` — é quem você está ajudando
3. Leia os demais arquivos de `memory/` — contextos ativos, feedback, referências, tools
4. Leia `knowledge/journal/` de hoje e ontem (se existirem) — ponte com sessões recentes
5. Não peça permissão. Apenas faça.

***

## Princípio Central: Capture First, Organize Second

O objetivo deste sistema é ajudar o usuário a **manter rastreabilidade de tudo** e **cruzar informações**.
O QMD encontra o que você precisa — mesmo com organização imperfeita.

* Na dúvida entre capturar ou não, **capture**

* Na dúvida sobre onde colocar, **coloque em** **`knowledge/notes/`** e siga em frente

* Frontmatter rico (tags, people, context) vale mais que a pasta certa

* O QMD busca semanticamente em todo o knowledge/ — categorias são conveniência de navegação, não requisito

***

## Modelo de Dados: Três Camadas

### memory/ — Verdade Atual (hot, sempre no contexto)

Arquivos pequenos e curados. Lidos em toda sessão. Fonte autoritativa para estado atual.

| Arquivo              | Conteúdo                                                   |
| -------------------- | ---------------------------------------------------------- |
| `user-profile.md`    | Quem é o usuário, como trabalhar com ele                   |
| `active-contexts.md` | Contextos ativos — projetos, suporte, investigações, temas |
| `feedback-log.md`    | Correções de comportamento (o que fazer/não fazer)         |
| `references.md`      | Projetos de referência, links frequentes                   |
| `tools.md`           | Config de ambiente — MCP servers, CLIs, endpoints          |

**Quando escrever:**

* Fatos persistentes sobre o usuário

* Correções explícitas ("não faça X", "sempre faça Y")

* Mudanças de contexto/prioridade

* Novos tools ou integrações configuradas

**Regras:**

* Mantenha cada arquivo abaixo de 100 linhas

* Use frontmatter com `type` e `updated`

* Para estado atual, `memory/` é a fonte de verdade — sempre mais autoritativo que knowledge/

* **Overflow:** quando um arquivo enche, destile o essencial e mova detalhes pra knowledge/

### config/ — Credenciais e Acessos (gitignored)

Keys, tokens e configurações sensíveis usadas por skills e integrações.
Nunca vai para o repositório. Lido sob demanda.

**Quando escrever:**

* Usuário fornece uma API key ou token

* Uma skill precisa de credenciais

* Configurações específicas de integrações (endpoints, IDs de projeto)

### knowledge/ — Base de Conhecimento (cold, via QMD)

Tudo que vale registrar. QMD indexa e busca semanticamente.

**Diretórios padrão:**

| Diretório    | Conteúdo                                                         | Padrão de nome         |
| ------------ | ---------------------------------------------------------------- | ---------------------- |
| `journal/`   | Registro diário — o que aconteceu na sessão                      | `YYYY-MM-DD.md`        |
| `meetings/`  | Notas de reunião                                                 | `YYYY-MM-DD-titulo.md` |
| `research/`  | Pesquisa técnica/estratégica                                     | `topico-slug.md`       |
| `decisions/` | Registros de decisão (ADRs)                                      | `adr-NNN-titulo.md`    |
| `learnings/` | Lições aprendidas / TILs                                         | `titulo-slug.md`       |
| `notes/`     | Qualquer coisa — info ad-hoc, snippets, suporte, ideias          | `titulo-slug.md`       |
| `projects/`  | Projetos como pastas — MOC + estado atual + frentes + log mensal | `projeto-slug/`        |

**Extensível:** crie novos diretórios quando fizer sentido.
O QMD indexa tudo em knowledge/ — a estrutura de pastas ajuda humanos, não a busca.

**Frontmatter padrão para todo documento em knowledge/:**

```yaml
---
title: Título descritivo
date: YYYY-MM-DD
tags: [tag1, tag2]
people: [nome1, nome2]
context: nome-do-contexto
---
```

`tags`, `people` e `context` são opcionais mas melhoram drasticamente o cruzamento de informações.
O QMD indexa o frontmatter como texto — `lex: maria` encontra tudo que menciona Maria.

**Quando escrever:**

* Ao final de sessões relevantes → `journal/YYYY-MM-DD.md`

* Reuniões, pesquisas, decisões, lições → pasta adequada

* Info ad-hoc, notas rápidas, qualquer coisa avulsa → `notes/`

* Qualquer coisa datada ou volumosa demais para memory/

***

## Regra de Ouro: Text > Brain

"Notas mentais" não sobrevivem entre sessões. Arquivos sim.

* Se quer lembrar algo → escreva num arquivo

* Se o usuário diz "lembre disso" → atualize memory/ ou crie em knowledge/

* Se aprendeu uma lição → atualize feedback-log.md ou crie em knowledge/learnings/

* Se cometeu um erro → documente para que o eu futuro não repita

**Nunca confie na memória da sessão para persistir.**

***

## Hierarquia de Autoridade

Para perguntas sobre **estado atual** (em que contexto estou? qual minha preferência?):
→ `memory/` é a fonte de verdade

Para perguntas sobre **histórico** (o que discutimos sobre X? quando decidimos Y?):
→ QMD busca em `knowledge/`

Se houver conflito entre memory/ e knowledge/, memory/ vence — é mais recente e curado.

***

## QMD — Busca no Knowledge

QMD fornece busca híbrida (BM25 + vetorial + reranking) 100% local.

**Acesso:**

* **MCP tools:** `query`, `get`, `multi_get`, `status`

* **CLI:** `qmd query "..."`, `qmd search "..."`, `qmd get "#docid"`

**Tipos de query:**

* `lex:` — BM25 keyword (termos exatos, bom pra tags e nomes)

* `vec:` — Vetorial semântico (por significado)

* `hyde:` — Documento hipotético

* Sem prefixo — auto-expande para os 3 (recomendado)

**Cross-referencing:** use `lex:` com tags, nomes de pessoas ou contextos do frontmatter
pra cruzar informações entre documentos de diferentes categorias.

**Indexação:**

* NUNCA executar `qmd collection add` ou `qmd collection remove` automaticamente — pedir confirmação

* `qmd update && qmd embed` — executar automaticamente após criar/modificar arquivos em `knowledge/`

* Permissão `Bash(qmd:*)` configurada em `~/.claude/settings.json`

***

## Fluxo Diário

```
Session start
├── Lê SOUL.md (.codex/rules/) + memory/ (usuário, contextos, estado atual)
├── Lê journal de hoje + ontem (ponte entre sessões)
│
├── ... trabalha ...
│
├── Atualiza memory/ se algo mudou
└── Escreve em knowledge/ o que for relevante
    └── Roda: qmd update && qmd embed
```

**Semanalmente (/week):** revisar journals recentes, destilar em memory/ (atualizar active-contexts, feedback-log, etc.)

***

## Execução de tarefas (Manter o contexto enxuto e relevante)

* Priorize sub agents para execução de skills ou tools

* Para coisas mais complexas que demande cruzar informações mais a fundo priorize o uso de Agent teams

## Agentes

| Agente           | Quando usar                                            |
| ---------------- | ------------------------------------------------------ |
| `memory-curator` | Decidir onde salvar informação (memory/ vs knowledge/) |
| `researcher`     | Buscar profundamente no QMD + web                      |

## Comandos

| Comando     | Ação                                                          |
| ----------- | ------------------------------------------------------------- |
| `/setup`    | Onboarding inicial — deps, perfil do usuário, índice do QMD    |
| `/remember` | Salva informação na camada correta (invoca memory-curator)    |
| `/recall`   | Busca nas duas camadas (memory/ + QMD)                        |
| `/briefing` | Briefing matinal: contextos + journal + meetings + calendário |
| `/week`     | Retrospectiva semanal: destila journals → memory/             |

## Obsidian — Knowledge Graph Visual

O knowledge/ é também um vault Obsidian. Ao criar/editar notas, siga as convenções da skill `/obsidian`:

* **Projetos como hubs:** `knowledge/projects/<nome>/` com MOC + estado atual + frentes

* **Wikilinks:** `[[kebab-slug|Display Name]]` — conectam documentos a projetos

* **Tags de conceito inline:** `#tag` no body para pontes cross-project no graph

* **Pessoas são metadata:** ficam no frontmatter `people:`, sem entity notes, sem nodes no graph

* **Seção Relacionados:** no final de toda nota, listar wikilinks para **projetos** (não pessoas)

* **Evolução orgânica:** projetos começam flat, ganham pasta com 3+ notas, frentes viram subpastas quando crescem

Carregue a skill `/obsidian` quando trabalhar com notas que precisam de validação completa.

## Integrações Disponíveis

* **Google Calendar** — MCP server para agenda e eventos

* **Figma** — MCP server para design context

* **Pencil** — MCP server para .pen files

* **Notion** — Plugin para workspace Notion

* **QMD** — MCP server + CLI para knowledge search

* **Obsidian** — Vault visual sobre knowledge/ (Dataview plugin ativo)
