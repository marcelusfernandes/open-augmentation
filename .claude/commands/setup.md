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

Opcionais (transcriber — instale conforme o backend escolhido na Fase 3):
- **ffmpeg** (sempre — grava/converte áudio) — macOS: `brew install ffmpeg`; Windows: `winget install ffmpeg` (ou `scoop install ffmpeg`)
- **Captura de áudio do sistema:**
  - macOS — **BlackHole 2ch**: `brew install --cask blackhole-2ch`; e **Swift**: `xcode-select --install` (a skill cria o Multi-Output Device sozinha)
  - Windows — **PyAudioWPatch**: `pip install PyAudioWPatch` (captura via WASAPI loopback nativo — sem driver, sem VB-CABLE, sem mexer em config de som). Sem ele, só mic presencial e transcrição de arquivos existentes funcionam.
- Se **AssemblyAI**: `pip install assemblyai`
- Se **local**: `pip install pywhispercpp sherpa-onnx soundfile` (whisper.cpp + diarização ONNX; sem conta/key). No macOS usa Metal/GPU; no Windows roda em CPU (mais lento, mas funciona).

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
- Quais MCP servers quer (Calendar, Notion, Figma...)? Anote os habilitados em tools.md.
- Confirme timezone em tools.md.

**Transcrição de reuniões (skill `transcriber`):**
Pergunte se o usuário quer usar o transcriber. Se sim, ofereça a escolha do motor de
transcrição (use AskUserQuestion). Apresente a diferença assim — factual, sem alarmar:

> Os dois transcrevem bem; a diferença é **onde o áudio é processado**:
> - **Local (Whisper na sua máquina)** — o áudio nunca sai da máquina, é de graça e não
>   precisa de conta. É mais lento: uma reunião de 1h leva ~15-20min processando em
>   background depois que você para a gravação. No macOS usa a GPU (Metal); no Windows
>   roda em CPU (funciona, só mais lento).
> - **AssemblyAI (nuvem)** — o áudio é enviado pros servidores do AssemblyAI pra
>   transcrever e removido depois conforme a política deles. É rápido (minutos) e um
>   pouco melhor em nomes próprios. A conta gratuita cobre uso pessoal de sobra.
>
> Escolha **local** se prefere manter tudo na máquina; **AssemblyAI** se quer velocidade
> e não se incomoda que o áudio passe pela nuvem. Dá pra trocar depois.

Conforme a escolha:

- **AssemblyAI:**
  1. Criar conta grátis em https://www.assemblyai.com — o **tier gratuito é suficiente
     pra uso pessoal** (não precisa plano pago).
  2. Copiar a API key no dashboard.
  3. Gravar em `config/assemblyai.json`: `{"api_key": "<sua-key>"}` (gitignored — nunca
     vai pro repositório).

- **Local:** instalar `pywhispercpp` (whisper.cpp; Metal no Mac, CPU no Windows) + `sherpa-onnx`
  (diarização via ONNX) e baixar os modelos (~35MB de diarização + o modelo Whisper).
  Recomende **`medium`** (padrão — equilíbrio pt-BR × velocidade; já empata com a nuvem no
  essencial). `large-v3` existe, mas é download de ~3GB e bem mais lento, com ganho marginal
  pra reunião — só vale se precisar de precisão máxima. Sem conta, sem key, sem custo.

Registre a escolha em `memory/tools.md` (`transcription_backend: local | assemblyai`).

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
