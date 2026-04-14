---
name: stepaudio-asr-2p5
description: "Use this skill whenever the user wants to transcribe audio with the stepaudio-asr-2p5 service or another custom/private ASR service that exposes an HTTP SSE transcription endpoint instead of the built-in StepFun ASR backend. Triggers include mentions of stepaudio-asr-2p5, a new ASR service, internal ASR endpoint, custom API URL, private speech-to-text backend, or requests to pass API URL / API key / model explicitly for audio transcription. Do NOT use this skill for StepFun-specific ASR requests when the existing step-asr skill already matches."
version: 0.1.0
metadata:
  openclaw:
    emoji: "\U0001F399"
    requires:
      bins:
        - python3
      env:
        - CUSTOM_ASR_API_KEY
        - CUSTOM_ASR_API_URL
        - CUSTOM_ASR_MODEL
    primaryEnv: CUSTOM_ASR_API_KEY
---

# stepaudio-asr-2p5

Transcribe audio files with a custom ASR service that accepts HTTP SSE requests.

Use this skill when the backend is **not the built-in StepFun ASR skill**, and
the user provides or expects a custom API endpoint, API key, model name, VAD
options, or other service-specific settings.

## Triggers

- new ASR service / custom ASR service / private ASR service
- internal ASR endpoint / custom speech-to-text API / SSE ASR backend
- 公司的 ASR 服务 / 自建 ASR 接口 / 私有语音识别服务
- pass API URL / model / API key explicitly for transcription
- reuse the custom SSE request flow instead of the StepFun-only ASR skill

If the user explicitly wants **StepFun / 阶跃星辰** ASR, prefer `step-asr`
instead of this skill.

## Quick start

Configure the endpoint, key, and model:

```bash
export CUSTOM_ASR_API_URL="https://example.com/v1/audio/asr/sse"
export CUSTOM_ASR_API_KEY="YOUR_API_KEY"
export CUSTOM_ASR_MODEL="your-asr-model"
```

Then run:

```bash
python3 {baseDir}/scripts/transcribe.py /path/to/audio.wav
```

## Usage examples

Basic transcription with env-based configuration:

```bash
python3 {baseDir}/scripts/transcribe.py /path/to/audio.wav
```

Pass endpoint and model explicitly:

```bash
python3 {baseDir}/scripts/transcribe.py /path/to/audio.wav \
  --api-url "https://example.com/v1/audio/asr/sse" \
  --api-key "YOUR_API_KEY" \
  --model "your-asr-model"
```

Specify language and save to file:

```bash
python3 {baseDir}/scripts/transcribe.py /path/to/audio.mp3 \
  --language en \
  --out /tmp/transcript.txt
```

Use a prompt plus VAD settings:

```bash
python3 {baseDir}/scripts/transcribe.py /path/to/audio.wav \
  --prompt "请记录下你所听到的语音内容。" \
  --vad-type server_vad \
  --silence-duration-ms 700
```

Output structured JSON:

```bash
python3 {baseDir}/scripts/transcribe.py /path/to/audio.wav --json
```

## Important options

| Flag | Default | Description |
|------|---------|-------------|
| `--api-url` | `CUSTOM_ASR_API_URL` | SSE ASR endpoint URL |
| `--api-key` | `CUSTOM_ASR_API_KEY` | Bearer token for the service |
| `--model` | `CUSTOM_ASR_MODEL` | Model name required by the service |
| `--language` | `auto` | Language hint |
| `--prompt` | `请记录下你所听到的语音内容。` | Prompt / system instruction for transcription |
| `--audio-type` / `--format-type` | auto | Audio type inferred from extension unless overridden |
| `--audio-codec` | auto | Audio codec inferred from type unless overridden |
| `--sample-rate` | `16000` | Sample rate in Hz |
| `--audio-bits` | `16` | Bits per sample |
| `--audio-channel` | `1` | Channel count |
| `--vad-type` | `server_vad` | VAD mode sent as query param |
| `--silence-duration-ms` | `700` | End-of-speech silence threshold |
| `--user-id` | *(none)* | Optional `X-User-Id` header |
| `--no-stream` | `false` | Only print the final result |
| `--json` | `false` | Print a JSON object with metadata |
| `--out` | *(stdout)* | Save transcript or JSON to file |

## Environment variables

Preferred variables:

- `CUSTOM_ASR_API_URL`
- `CUSTOM_ASR_API_KEY`
- `CUSTOM_ASR_MODEL`

Compatibility aliases also supported:

- `ASR_SSE_URL`
- `ASR_SSE_KEY`
- `ASR_SSE_API_URL`
- `ASR_SSE_API_KEY`
- `ASR_SSE_MODEL`

## Agent guidance

- Use this skill only when the task clearly targets a **custom / private** ASR
  backend or needs an explicit endpoint URL.
- If the user does not provide the endpoint URL, API key, or model, check the
  environment variables above before asking.
- Keep `step-asr` as the default choice for StepFun-specific ASR requests.
