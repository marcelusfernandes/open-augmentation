---
description: Onboarding inicial — instala dependências, coleta o perfil do usuário e deixa o sistema pronto pra uso
---

Você está rodando o **setup inicial** do Augmentation para um usuário novo. Conduza
como uma conversa curta e objetiva, não um questionário robótico. O objetivo é sair
com o sistema funcionando: dependências checadas, `memory/` preenchido, `knowledge/`
estruturado e QMD indexando.

Trabalhe em fases. Em cada fase, AJA (rode comandos, crie arquivos) e só pergunte o
que não dá pra inferir. Não peça permissão pra ler/escrever arquivos internos.

---

## Fase 0 — Detectar estado

Verifique se já existe setup prévio:

```
ls memory/user-profile.md 2>/dev/null && echo "JÁ EXISTE memory/" || echo "memory/ vazio"
```

Se `memory/` já estiver preenchido, **NÃO sobrescreva** — pergunte se o usuário quer
re-rodar do zero (e qual parte) ou só completar lacunas. Se vazio, siga em frente.

---

## Fase 1 — Dependências

Cheque o que está instalado e reporte uma tabela `OK / FALTA` com o comando de
instalação ao lado. Não instale nada sem confirmar.

```
which qmd node python3 ffmpeg gh 2>/dev/null
qmd --version 2>/dev/null
```

Essenciais e como instalar:
- **Node.js + npm** — https://nodejs.org (necessário pro QMD)
- **QMD** — `npm install -g @tobilu/qmd` (busca local do knowledge/). Se `head $(which qmd)` mostrar `#!/usr/bin/env bun`, troque a shebang pra `node` — sqlite-vec quebra sob bun.
- **Python 3.9+** — necessário só pro transcriber (opcional)

Opcionais (transcriber):
- **ffmpeg** — `brew install ffmpeg`
- **pip install assemblyai**
- **BlackHole 2ch** (captura de áudio do sistema, macOS) — `brew install --cask blackhole-2ch`
- **Swift** (macOS) — `xcode-select --install`

Se faltar essencial, liste o comando e pergunte se quer que você rode (ou que o
usuário rode via `! <comando>`). Não trave o setup por dependência opcional.

---

## Fase 2 — Scaffold de pastas

Crie a estrutura local (gitignored) a partir dos templates, sem sobrescrever nada
que já exista:

```
mkdir -p memory config knowledge/_private recordings
for f in templates/memory/*.md; do
  base=$(basename "$f")
  [ -f "memory/$base" ] || cp "$f" "memory/$base"
done
[ -f config/assemblyai.json ] || cp templates/config/assemblyai.json.example config/assemblyai.json.example
```

Confirme que `knowledge/` tem os diretórios padrão (já vêm com `_template.md`):
journal, meetings, notes, research, decisions, learnings, projects, people.

---

## Fase 3 — Entrevista (preenche memory/ + SOUL)

Colete o mínimo necessário, de forma conversacional. Sugiro usar a ferramenta de
perguntas (AskUserQuestion) pra agrupar. Itens:

**Identidade (→ `memory/user-profile.md`):**
- Nome e como prefere ser chamado
- Idiomas (ex: pt-BR, en-US)
- Timezone
- Função / título e organização (se houver)
- Stakeholders / time principal (se houver)
- Como trabalha melhor (direto vs. discussão; explora vs. executa; recomendação vs. opções)
- Foco atual / objetivos

**Tom (→ seção "Tom" de `.claude/rules/SOUL.md`):**
- Como o assistente deve soar? (formal, casual, direto, bem-humorado, com gírias?)
- Quão proativo? Pode agir em ações internas sem pedir, mas confirma externas?
  Escreva isso no bloco "Tom personalizável" do SOUL, substituindo o placeholder.

**Contextos ativos (→ `memory/active-contexts.md`):**
- 2-5 projetos/temas em andamento agora (nome + status + 1 linha)

**Ambiente & integrações (→ `memory/tools.md` + `config/`):**
- Vai usar transcriber? Se sim, peça a API key do AssemblyAI (https://www.assemblyai.com)
  e grave em `config/assemblyai.json` (gitignored).
- Quais MCP servers quer (Calendar, Notion, Figma...)? Anote os habilitados em tools.md.
- Confirme timezone em tools.md.

Escreva cada resposta no arquivo correspondente, mantendo o frontmatter e atualizando
`updated:` pra data de hoje. Mantenha cada arquivo de memory/ abaixo de 100 linhas.

---

## Fase 4 — QMD (indexação)

Inicialize a coleção do knowledge/. **Peça confirmação antes de `qmd collection add`**
(regra do sistema — nunca rodar automaticamente):

```
qmd collection add <caminho-absoluto-do-repo>/knowledge   # SÓ após confirmar
qmd update && qmd embed
```

O primeiro `embed` baixa modelos (~2GB) — avise que pode demor. Depois teste:

```
qmd query "test"
```

---

## Fase 5 — Validação

Cheque e reporte:
- `memory/` tem os 5 arquivos preenchidos (não placeholders)
- SOUL.md tem o tom definido (sem o placeholder genérico)
- `qmd query` responde
- Dependências essenciais OK

Feche com um resumo curto: o que ficou pronto, o que ficou pendente (deps opcionais
não instaladas), e diga que a primeira sessão real começa lendo SOUL + memory/.

> Não commite `memory/`, `config/` nem `recordings/` — são gitignored por design.
