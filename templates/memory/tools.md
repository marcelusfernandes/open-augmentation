---
name: tools
description: Config de ambiente — tools, MCP servers, CLIs e detalhes de setup
type: tools
updated: YYYY-MM-DD
---

# Tools & Ambiente

> Config local da máquina. Detalhes sensíveis (keys, tokens) vão em `config/`
> (gitignored), não aqui — aqui ficam só ponteiros e flags de "está configurado".

## QMD (busca no knowledge/)

- Instalado via npm global: `npm install -g @tobilu/qmd`
- Coleção aponta para: `<repo>/knowledge`
- Reindex: `qmd update && qmd embed`

## Transcriber (opcional)

- `transcription_backend:`  <!-- local | assemblyai (escolhido no /setup) -->
- Comum: ffmpeg, swift + BlackHole (macOS)
- Se **assemblyai**: `pip install assemblyai` + key em `config/assemblyai.json` (conta grátis basta)
- Se **local**: `pip install pywhispercpp sherpa-onnx soundfile` (whisper.cpp/Metal + diarização ONNX; sem conta/key; áudio fica na máquina)

## MCP servers configurados

- QMD (essencial)
- <outros que você habilitar: Google Calendar, Notion, Figma...>

## Preferências de ambiente

- Timezone:
