---
name: transcribe
description: Gravar e transcrever reuniões, gerando notas estruturadas em knowledge/meetings/. Use quando o usuário pedir para gravar uma reunião, transcrever áudio, ou processar uma gravação existente.
allowed-tools: Bash(python3 *), Read, Write, Edit, Glob
---

# Meeting Transcriber

Grava reuniões e gera notas estruturadas em `knowledge/meetings/` com frontmatter, transcrição por speaker, e wikilinks.

## Como Funciona

Script único em `${CLAUDE_SKILL_DIR}/scripts/transcriber.py` com subcomandos:
- **`devices`** — lista devices de áudio disponíveis
- **`record`** — grava áudio (meeting mode por padrão: mic + remote)
- **`stop`** — para a gravação em andamento
- **`transcribe`** — envia pra AssemblyAI, retorna JSON com transcrição + speakers

Config (API key) em `config/assemblyai.json` (gitignored).

**Importante:** `record` roda em background (via `Bash` com `run_in_background: true`). O processo FFmpeg fica gravando até receber `stop`. Isso libera o prompt pro usuário continuar conversando.

## Fluxos

### 1. Listar devices

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py devices
```

### 2. Gravar reunião

**Padrão** — sempre grava remote + mic mixados (meeting mode):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py record <remote_device> [mic_device]
```

Exemplo Zoom: `record 2` (ZoomAudioDevice + MacBook Mic default)
Exemplo Teams: `record 3 1` (Teams Audio + MacBook Mic)

O `mic` default é `1` (MacBook Pro Microphone). Só precisa passar se for outro.

**Single device** (raro — só se precisar de um device isolado):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py record <device> --single
```

A gravação salva em `recordings/rec_YYYYMMDD-HHMMSS.wav`. O PID fica em `recordings/.recording.pid`.

Lançar com `Bash` usando `run_in_background: true` para não bloquear o prompt.

### 2b. Parar gravação

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py stop
```

Envia SIGINT pro FFmpeg, que finaliza o arquivo WAV corretamente.

**Devices comuns:**
- `3` = Microsoft Teams Audio (reuniões do Teams)
- `2` = ZoomAudioDevice (reuniões do Zoom)
- `1` = MacBook Pro Microphone (presencial)

### 3. Transcrever áudio

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py transcribe <caminho_do_audio>
```

Retorna JSON com: `text`, `speakers`, `utterances` (com speaker labels), `audio_duration`, `language`.

### 4. Gerar nota de reunião

Com a transcrição em mãos, gerar um `.md` em `knowledge/meetings/` seguindo este formato:

```yaml
---
title: "Título descritivo da reunião"
date: YYYY-MM-DD
tags: [meeting, tag1, tag2]
people: [Nome Completo 1, Nome Completo 2]
context: slug-do-projeto
---
```

#### Corpo da nota:

1. **Contexto** — 1-2 frases sobre o que era a reunião
2. **Participantes** — lista com papel de cada um (se identificável)
3. **Discussão** — pontos principais organizados por tópico, NÃO cronologicamente
4. **Decisões** — o que foi decidido, com contexto
5. **Action Items** — `- [ ]` com responsável e prazo se mencionado
6. **Relacionados** — wikilinks para projetos relevantes

#### Regras:

- **Identifica pessoas pelos nomes** que aparecem na conversa, não por "Speaker A/B"
- Se não conseguir identificar, pergunta pro usuário
- **Agrupa por tópico**, não transcreve linearmente — ninguém quer ler transcrição bruta
- **Extrai o que importa**: decisões, ações, insights. O resto é contexto
- **Tags de conceito inline** se algum trecho tiver conexão cross-project
- **Tom natural** — escreve como o usuário escreveria, não como ata formal
- Depois de salvar, roda `qmd update && qmd embed`

### 5. Processar gravação existente

Se o usuário já tem um arquivo de áudio (qualquer formato que FFmpeg suporte):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py transcribe ~/caminho/para/audio.wav
```

Mesmo fluxo de geração de nota.

## O que NÃO fazer

- Não transcreve literalmente — sintetiza
- Não inventa informação que não está na transcrição
- Não grava sem o usuário pedir explicitamente
- Não comita arquivos de áudio no git (recordings/ deve estar no .gitignore)
