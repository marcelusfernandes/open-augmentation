# Augmentation

Um sistema de **memória persistente e knowledge-management** que roda sobre o
**[Claude Code](https://claude.com/claude-code)**. O assistente "acorda do zero" a
cada sessão e carrega sua identidade, contexto atual e conhecimento histórico a partir
de arquivos — então tudo que importa vira texto **versionável e buscável**, não memória
volátil de chat.

> Princípio central: **Capture First, Organize Second.** Na dúvida, capture. A busca
> semântica (QMD) encontra depois, mesmo com organização imperfeita.

---

## O que ele faz

| Funcionalidade | Como você usa |
| --- | --- |
| 🧠 **Memória entre sessões** — perfil, preferências, contextos ativos e correções vivem em `memory/` e são lidos toda sessão | Automático; você ajusta com `/remember` |
| 🔎 **Busca semântica** no seu conhecimento (BM25 + vetorial + reranking, 100% local via QMD) | `/recall` ou `qmd query "..."` |
| 📝 **Captura inteligente** — salva cada informação na camada certa (hot vs cold) | `/remember <algo>` |
| 🎙️ **Gravar e transcrever reuniões** — Zoom/Teams/presencial, com notas estruturadas e identificação de quem falou. **macOS e Windows.** | "grava aí no zoom" → "para" → "transcreve" |
| ☀️ **Briefing matinal** — contextos + journal + reuniões + agenda do dia | `/briefing` |
| 🔁 **Retrospectiva semanal** — destila os journals da semana de volta pra `memory/` | `/week` |
| 📊 **Status executivo semanal** de um projeto (semana ISO, seg–dom) | `/weekly-status <projeto>` |
| 🕸️ **Knowledge graph no Obsidian** — projetos como hubs, pessoas como metadata, tags como pontes | abra `knowledge/` no Obsidian |
| 🔌 **Integrações** via MCP — Google Calendar, Notion, Figma | configuradas no `/setup` |

A arquitetura completa está em **[`CLAUDE.md`](CLAUDE.md)** e a persona do assistente em
**[`.claude/rules/SOUL.md`](.claude/rules/SOUL.md)** (personalizável no `/setup`).

---

## Como funciona — três camadas

| Camada | O que é | Versionado? |
| --- | --- | --- |
| `memory/` | **Verdade atual (hot).** Perfil, contextos ativos, feedback, referências, tools. Lido em toda sessão. | Não (local) |
| `config/` | **Credenciais e keys** usadas por skills/integrações. | Não (local) |
| `knowledge/` | **Base de conhecimento (cold).** Journal, reuniões, projetos, pessoas, decisões, pesquisas. Indexada e buscada pelo QMD. | Sim |

Regra de autoridade: para **estado atual**, `memory/` manda; para **histórico**, o QMD
busca em `knowledge/`. Se conflitar, `memory/` vence (é mais recente e curado).

---

## Setup

1. **Instale o [Claude Code](https://claude.com/claude-code)** e abra este repositório nele.

2. **Dependências de sistema** (o `/setup` checa e te guia — o essencial):

   ```bash
   # QMD — busca local do knowledge/ (essencial, multiplataforma)
   npm install -g @tobilu/qmd
   ```
   > Se `head $(which qmd)` mostrar `#!/usr/bin/env bun`, troque a shebang pra `node`
   > — o `sqlite-vec` quebra sob bun.

   **Opcionais — só pra skill de transcrição:**

   | | macOS | Windows |
   | --- | --- | --- |
   | Áudio (sempre) | `brew install ffmpeg` | `winget install ffmpeg` |
   | Áudio do sistema | `brew install --cask blackhole-2ch` | `pip install PyAudioWPatch` *(WASAPI nativo — sem driver)* |
   | Backend **local** (sem key) | `pip install pywhispercpp sherpa-onnx soundfile` | idem |
   | Backend **nuvem** (AssemblyAI) | `pip install assemblyai` | idem |

3. **Rode o onboarding** dentro do Claude Code:

   ```
   /setup
   ```
   Ele instala/checa dependências, cria `memory/` e `config/` a partir de `templates/`,
   te entrevista (nome, tom do assistente, contextos ativos, integrações, backend de
   transcrição) e inicializa o índice do QMD. Em poucos minutos está pronto.

---

## Uso no dia a dia

### Comandos

| Comando | O que faz |
| --- | --- |
| `/briefing` | Briefing matinal: contextos + journal + reuniões + agenda |
| `/remember <algo>` | Salva uma informação na camada certa (invoca o agente `memory-curator`) |
| `/recall <busca>` | Busca nas duas camadas (memory/ + knowledge/) |
| `/week` | Retrospectiva semanal: destila journals → `memory/` |
| `/weekly-status <projeto>` | Status executivo da última semana ISO de um projeto |
| `/setup` | Onboarding / reconfiguração |

Depois de criar ou editar qualquer coisa em `knowledge/`, reindexe:

```bash
qmd update && qmd embed
```

### Gravar e transcrever reuniões

A skill entende **linguagem natural** — você não passa flags. Exemplos:

```
você:  grava aí, tô no zoom
você:  (reunião acontece…) pode parar
você:  transcreve aí
```

O assistente grava (remoto + microfone mixados), gera a transcrição, **identifica quem
falou** (cruzando com `knowledge/people/`) e salva uma **nota estruturada** em
`knowledge/meetings/` — contexto, participantes, discussão por tópico, decisões e action
items. Também funciona com `"grava o teams"`, `"grava o áudio do computador"` (vídeo,
podcast), `"grava só o microfone"` (presencial) ou um arquivo já existente.

Dois backends, escolhidos no `/setup`:
- **Local** (whisper.cpp + diarização ONNX) — áudio nunca sai da máquina, sem conta/key.
  GPU no Mac (Metal), CPU no Windows.
- **AssemblyAI** (nuvem) — rápido; conta gratuita cobre uso pessoal.

Captura de **áudio do sistema** (Zoom/Teams/qualquer app): no macOS via BlackHole, no
Windows via **WASAPI loopback nativo** — sem driver, sem mexer em config de som.

---

## Estrutura

```
.
├── CLAUDE.md            # Manual operacional (lido toda sessão)
├── .claude/             # Skills, agentes, comandos, regras, settings
│   ├── commands/        # /setup /briefing /remember /recall /week /weekly-status
│   ├── agents/          # memory-curator, researcher
│   ├── skills/          # transcriber, obsidian
│   └── rules/SOUL.md    # Persona do assistente (definida no /setup)
├── .codex/              # Espelho de comandos/regras pro Codex CLI
├── memory/              # (local) preenchido pelo /setup a partir de templates/
├── config/              # (local) credenciais e keys
├── knowledge/           # base versionada — só _template.md no estado limpo
└── templates/           # scaffolds de memory/ e config/ usados pelo /setup
```

---

## Privacidade

`memory/`, `config/`, `recordings/` e `knowledge/_private/` são **gitignored** por design
— seus dados pessoais e gravações nunca vão pro repositório. Só `knowledge/` (fora de
`_private/`) é versionado, então você decide o que mora onde. Com o backend de
transcrição **local**, o áudio também nunca sai da sua máquina.

---

## Licença

[MIT](LICENSE).
