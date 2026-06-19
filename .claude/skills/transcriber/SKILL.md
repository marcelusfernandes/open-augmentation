---
name: transcribe
description: Gravar e transcrever reuniões, gerando notas estruturadas em knowledge/meetings/. Use quando o usuário pedir para gravar uma reunião, transcrever áudio, ou processar uma gravação existente.
allowed-tools: Bash(python3 *), Read, Write, Edit, Glob
---

# Meeting Transcriber

Grava reuniões e gera notas estruturadas em `knowledge/meetings/` com frontmatter, transcrição por speaker, e wikilinks.

## Interpretando o pedido do usuário

O usuário fala natural — não passa flag nenhuma. **Tu** mapeia a frase pro device certo. Esta tabela é o contrato — siga sem perguntar (a não ser que a frase seja realmente ambígua):

| Frase do usuário | Comando |
|------------------|---------|
| "grava aí no zoom" / "tô no zoom" / "começa a gravar, é zoom" | `record zoom` |
| "grava no teams" / "reunião no teams" / "tô no teams agora" | `record teams` |
| "grava o áudio do computador" / "grava o que tá tocando" / "grava esse vídeo" / "grava esse podcast" | `record system` |
| "grava aí" sem contexto, mas tem reunião Zoom/Teams ativa visível no contexto recente | usa o app da reunião |
| "grava aí" sem contexto nenhum | **pergunta**: zoom, teams, ou áudio do sistema (computador)? |
| "grava só o microfone" / "grava presencial" / "tô numa reunião presencial" | `record mic --single` |
| "para a gravação" / "pode parar" / "já deu" | `stop` |
| "transcreve aí" (após stop) | `transcribe <pasta_da_sessão>` (local streaming) ou `transcribe <audio.wav>` |
| "transcreve esse áudio aqui [caminho]" | `transcribe <caminho>` |

**Pra `record system` (BlackHole):** o setup é automático. A skill cria o Multi-Output Device "BlackHole + Speakers" (idempotente, só cria na 1ª vez), salva qual era a saída padrão, troca pro Multi-Output e grava. No `stop`, restaura saída automaticamente. Não precisa pedir nada pro usuário — ele só ouve o som normal pelos speakers e o BlackHole captura em paralelo.

**Idioma do usuário:** ele alterna pt-BR/en-US — reconhece os dois ("record the zoom", "stop recording", "transcribe this", etc.).

### Windows

O mesmo script roda no Windows — só muda a camada de áudio. O fluxo de comandos (`record`/`stop`/`transcribe`) e a geração da nota são idênticos. Diferenças que importam pra interpretar o pedido:

- **Áudio do sistema = WASAPI loopback nativo** (`scripts/wasapi_record.py`, via `pyaudiowpatch`). Captura direto o que está tocando — **sem driver, sem VB-CABLE, sem mexer em config de som**, e o usuário continua ouvindo normal. É o equivalente do BlackHole no Mac, só que sem instalar nada além do pacote Python. Funciona automático: `record system` (ou `zoom`/`teams`) já dispara o capturador loopback + mic.
- **Não há captura virtual por app.** Zoom/Teams não expõem device próprio no Windows, então os aliases `zoom`, `teams` e `system` **todos** caem no mesmo loopback do sistema — "grava o zoom" no Windows = gravar tudo que o sistema toca + o mic. Não existe `record zoom` isolado como no Mac (mas o resultado é o mesmo: a fala do Zoom é capturada).
- **Pré-requisito** pra áudio do sistema: `pip install PyAudioWPatch`. Se faltar, o `record system` falha com a instrução exata. Mic presencial (`record mic --single`) e processar áudio existente usam só o ffmpeg.
- **Mic + áudio do sistema** são capturados juntos e mixados pelo próprio `wasapi_record.py` (mono 16k + chunks de 30s pro streaming) — os artefatos são idênticos aos do ffmpeg, então sidecar/stop/transcribe/diarização seguem iguais.
- **Captura de mic isolada e meetings por device DirectShow** usam ffmpeg (`-f dshow`).
- O `stop` é gracioso via arquivo-sentinela que o processo de gravação observa — mesmo comportamento visível pro usuário que no Mac.

## Como Funciona

Script único em `${CLAUDE_SKILL_DIR}/scripts/transcriber.py` com subcomandos:
- **`devices`** — lista devices de áudio disponíveis
- **`record`** — grava áudio (meeting mode por padrão: mic + remote)
- **`stop`** — para a gravação em andamento
- **`transcribe`** — transcreve + diariza, retorna JSON com transcrição + speakers

**Dois backends de transcrição** (escolhidos no `/setup`, gravado em `config/transcriber.json`):
- **`local`** (padrão recomendado no Mac) — whisper.cpp (Metal/GPU) + diarização ONNX via sherpa-onnx. Sem conta, sem key, áudio fica na máquina. Mais lento (diarização roda em CPU). Modelos baixam sozinhos na 1ª vez pra `config/transcriber-models/`.
- **`assemblyai`** — nuvem, rápido, key grátis em `config/assemblyai.json` (gitignored).

O `transcribe` resolve o backend por: flag `--backend` → `config/transcriber.json` → fallback (assemblyai se houver key, senão local).

**Streaming ASR (só backend local):** quando o backend é `local`, o `record` grava em chunks de 30s **e** transcreve cada chunk ao vivo num sidecar em background. Quando o usuário dá `stop`, o **texto já está pronto** em `<sessão>/transcript.partial.txt` (sem speakers ainda) — dá pra analisar na hora. O `transcribe` depois só faz a **diarização** (quem falou) no áudio completo, num passe rápido (~2-3 min pra 1h, `num_threads=4`), e gera o `transcript.txt` final com speakers. Tradeoff honesto: os cortes de 30s não dão contexto cruzado ao whisper, então o texto em streaming é marginalmente menos preciso nas bordas que o batch — na prática, irrelevante pra reunião. Desligar com `record ... --no-stream` (volta ao fluxo grava-tudo-depois-transcreve). No backend `assemblyai` não há streaming (é nuvem-batch).

**Importante:** `record` roda em background (via `Bash` com `run_in_background: true`). O processo FFmpeg fica gravando até receber `stop`. Isso libera o prompt pro usuário continuar conversando.

## Fluxos

### 1. Listar devices

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py devices
```

### 2. Gravar reunião

**Padrão** — sempre grava remote + mic mixados (meeting mode):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py record <remote> [mic]
```

Devices podem ser passados por **alias**, **nome (substring)** ou **índice numérico**.
Aliases recomendados (não dependem de índice — robusto a drivers novos):

| Alias | Resolve para (macOS) |
|-------|--------------|
| `mic` / `macbook` | MacBook Pro Microphone |
| `zoom` | ZoomAudioDevice |
| `teams` | Microsoft Teams Audio |
| `blackhole` / `system` | BlackHole 2ch (áudio do sistema) |

No **Windows** os aliases são outros (`mic` → microfone padrão; `system`/`zoom`/`teams` → loopback WASAPI do sistema) — ver a seção **Windows** acima. O script detecta a plataforma sozinho.

Exemplos:
- `record zoom` → Zoom + mic default
- `record teams` → Teams + mic default
- `record system` → áudio do **computador** (qualquer app) + mic — requer Multi-Output Device configurado (ver abaixo)

**Single device** (raro — só se precisar de um device isolado):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py record <device> --single
```

A gravação salva em `recordings/<DD-MM-YYYY-HH:MM>/audio.wav`. O PID fica em `recordings/.recording.pid`.

Lançar com `Bash` usando `run_in_background: true` para não bloquear o prompt.

### 2a. Gravar áudio do sistema (BlackHole) — automatizado

Pra gravar áudio que **não** vem de driver virtual de app (vídeo no browser, podcast, qualquer app que não tem driver próprio):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py record system
```

A skill faz tudo automaticamente via `audio_setup.swift` (CoreAudio):
1. Lê a saída padrão atual do sistema (ex.: MacBook Pro Speakers) e salva em `.previous_output`
2. Cria o Multi-Output Device "BlackHole + Speakers" se ainda não existir (idempotente)
3. Troca a saída do sistema pro Multi-Output (BlackHole captura + speakers continuam tocando)
4. Inicia ffmpeg

No `stop`, restaura a saída pra `.previous_output` e remove o arquivo de estado.

**Pré-requisito único:** ter o BlackHole 2ch instalado (`brew install --cask blackhole-2ch`). Tudo o resto é automático.

### 2b. Parar gravação

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py stop
```

Envia SIGINT pro FFmpeg, que finaliza o arquivo WAV corretamente. **No backend local com streaming**, o `stop` também finaliza o sidecar (processa o último chunk) e espera o texto drenar — quando retorna, `<sessão>/transcript.partial.txt` já tem a transcrição completa (sem speakers). Aí é só rodar `transcribe` na sessão pra diarizar e gerar a nota.

### 3. Transcrever áudio

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py transcribe <caminho_do_audio>
```

**Sessão em streaming (local):** se a gravação foi feita com streaming, passe a **pasta da sessão** (`transcribe recordings/<DD-MM-YYYY-HH:MM>`) — o `transcribe` detecta o `partial.jsonl`, pula o ASR (já feito ao vivo) e só diariza. Bem mais rápido.

**Arquivos da sessão (importante pros próximos passos):** a pasta `recordings/<DD-MM-YYYY-HH:MM>/` pode conter:
- `audio.wav` — gravação completa (fonte da diarização)
- `transcript.txt` — **transcript FINAL, com speakers (A/B/C). É ESTE que o speaker-matching e a nota usam.**
- `transcript.partial.txt` — texto ao vivo capturado durante a reunião, **sem speakers** — é só pra leitura rápida no meio da call. **Nunca usar pra matching nem pra nota.**
- `partial.jsonl` — buffer interno do streaming (ASR + timestamps), consumido pelo `transcribe`. Ignorar.
- `sidecar.log` / `.stop` — diagnóstico/controle do streaming. Ignorar.

A pasta e o `transcript.txt` têm o mesmo nome/formato dos dois backends — o fluxo pós-gravação (4a → nota → MOC → log) é idêntico, só sempre a partir do `transcript.txt`.

**Backend local:** se sabe quem estava na reunião (prior do setup da gravação — "gravando com Lucas e Bruno"), passe `--speakers N` — isso afia a diarização (sem o número, ele auto-detecta e pode superdividir). Modelo: `--whisper-model medium` (padrão — já empata com a nuvem no essencial). `large-v3` é ~3GB e bem mais lento, ganho marginal — evite a não ser que precise:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcriber.py transcribe <audio> --speakers 4 --whisper-model medium
```

Retorna JSON com: `text`, `speakers`, `utterances` (com speaker labels), `audio_duration`, `language` — mesmo formato nos dois backends.

### 4a. Speaker matching (ANTES de gerar a nota)

Os dois backends retornam speakers como labels anônimos ("A", "B", "C"…). **Nunca gerar a nota com Speaker A/B no corpo.** Antes:

1. **Conta os speakers** lendo o `transcript.txt` da sessão (o final, com labels A/B/C — **não** o `transcript.partial.txt`).
2. **Pra cada speaker**, capturar 1-2 utterances representativas (frases longas iniciais que dão pista de quem é).
3. **Buscar match** em `knowledge/people/` via QMD:
   ```bash
   qmd query "lex:<termos das falas ou nome se mencionado>"
   ```
   QMD lex bate em `name`/`aliases` do frontmatter — se a pessoa estiver lá, retorna a ficha.
4. **Apresentar bloco unificado pro usuário** antes de prosseguir:
   ```
   Identifiquei os speakers, confere ou corrige:
   Speaker A (12 falas, "tô puxando o crawler hoje..."): chuto Ana Silva
   Speaker B (8 falas, "do lado da observabilidade..."): chuto Bruno Costa
   Speaker C (3 falas, voz nova, "como é que vocês...")): não achei match — quem é?
   ```
5. O usuário responde curto: "tá certo" / "B é a Carla" / "C é o Daniel, novato, dev".
6. **Pra cada speaker confirmado:**
   - **Ficha existe** → enriquece `aliases:` se necessário, anexa projeto em `projects:` se ainda não tava, atualiza `updated:` pra hoje.
   - **Ficha NÃO existe** → assistant cria com 3 perguntas mínimas:
     1. Sobrenome / nome completo?
     2. Org: nome da organização, `external` ou `personal`?
     3. Role em 1 linha?
   - Preenche `_template.md`, salva em `people/<org>/<slug>.md`.

**Heurísticas:**
- Match exato em `name` ou `aliases` é forte — pode propor com confiança.
- Match fraco (só por conteúdo) → assistant nunca decide sozinho, sempre pergunta.
- Se o usuário disse no setup ("gravando reunião com a Ana e o Bruno"), isso vira **prior** que pré-popula o palpite.
- Em transcrições, palavras-chave recorrentes que cada pessoa usa ajudam a desambiguar — ex: quem fala muito de "infra/observabilidade" provavelmente é o dev de plataforma; quem cita "dados/pipeline" o de dados. Monte esse mapa por contexto do time.

### 4. Gerar nota de reunião

Com a transcrição em mãos e os speakers identificados, gerar um `.md` em `knowledge/meetings/` seguindo este formato:

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

- **Usa `name:` canônico** das fichas de `knowledge/people/` no frontmatter `people:` (não aliases). Se a pessoa não tem ficha ainda, a etapa 4a já cuidou de criar.
- Speaker labels do AssemblyAI (A/B/C) **só podem aparecer no corpo se a etapa 4a foi pulada por algum motivo justificado** — caso contrário, sempre nome real.
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
