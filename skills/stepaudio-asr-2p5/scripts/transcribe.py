#!/usr/bin/env python3
"""Transcribe audio files through a custom SSE ASR endpoint."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_PROMPT = "请记录下你所听到的语音内容。"
DEFAULT_CODEC_BY_TYPE = {
    "pcm": "pcm",
    "wav": "pcm",
    "mp3": "mp3",
    "ogg": "ogg",
    "opus": "opus",
    "flac": "flac",
}
FORMAT_MAP = {
    ".pcm": ("pcm", "pcm"),
    ".raw": ("pcm", "pcm"),
    ".wav": ("wav", "pcm"),
    ".mp3": ("mp3", "mp3"),
    ".ogg": ("ogg", "ogg"),
    ".opus": ("ogg", "opus"),
    ".flac": ("flac", "flac"),
}


def detect_format(filepath, override_type, override_codec):
    """Infer the type/codec pair from flags or file extension."""
    if override_type:
        codec = override_codec or DEFAULT_CODEC_BY_TYPE.get(override_type, "")
        return override_type, codec
    ext = os.path.splitext(filepath)[1].lower()
    detected_type, detected_codec = FORMAT_MAP.get(ext, ("wav", "pcm"))
    if override_codec:
        return detected_type, override_codec
    return detected_type, detected_codec


def load_env_value(cli_value, env_names):
    """Return CLI value first, then the first non-empty configured env var."""
    if cli_value:
        return cli_value
    for env_name in env_names:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return ""


def decode_json_stream(payload):
    """Yield JSON dicts from a concatenated JSON payload."""
    decoder = json.JSONDecoder()
    buffer = payload.strip()
    while buffer:
        item, offset = decoder.raw_decode(buffer)
        if isinstance(item, dict):
            yield item
        buffer = buffer[offset:].lstrip()


def iter_json_events(response):
    """Parse JSON SSE events from a streaming HTTP response."""
    pending_data_lines = []

    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            if pending_data_lines:
                yield from decode_json_stream("".join(pending_data_lines))
                pending_data_lines.clear()
            continue

        if line.startswith("event:"):
            continue

        if line.startswith("data:"):
            data_line = line[5:].strip()
            if data_line == "[DONE]":
                break
            pending_data_lines.append(data_line)
            continue

        yield from decode_json_stream(line)

    if pending_data_lines:
        yield from decode_json_stream("".join(pending_data_lines))


def build_request_body(audio_b64, args):
    """Build the JSON request body expected by the custom SSE ASR service."""
    audio_type, audio_codec = detect_format(
        args.audio_file,
        args.audio_type,
        args.audio_codec,
    )

    return {
        "audio": {
            "data": audio_b64,
            "input": {
                "transcription": {
                    "model": args.model,
                    "language": args.language,
                    "prompt": args.prompt,
                },
                "format": {
                    "type": audio_type,
                    "codec": audio_codec,
                    "rate": args.sample_rate,
                    "bits": args.audio_bits,
                    "channel": args.audio_channel,
                },
            },
        }
    }


def request_transcript(args):
    """Send the SSE request and return a normalized result object."""
    with open(args.audio_file, "rb") as handle:
        audio_b64 = base64.b64encode(handle.read()).decode("ascii")

    body = build_request_body(audio_b64, args)
    query = urllib.parse.urlencode(
        {
            "model": args.model,
            "vad_type": args.vad_type,
            "silence_duration_ms": args.silence_duration_ms,
        }
    )
    request_url = args.api_url
    if query:
        separator = "&" if "?" in request_url else "?"
        request_url = f"{request_url}{separator}{query}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {args.api_key}",
    }
    if args.user_id:
        headers["X-User-Id"] = args.user_id

    request = urllib.request.Request(
        request_url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    last_error = None
    for attempt in range(max(1, args.max_retries)):
        response = None
        send_time = time.perf_counter()
        try:
            response = urllib.request.urlopen(request, timeout=args.request_timeout)

            session_id = None
            first_delta_time = None
            delta_texts = []
            final_text = ""
            usage = {}

            for event in iter_json_events(response):
                meta = event.get("meta") or {}
                session_id = session_id or meta.get("session_id")

                event_type = event.get("type")
                if event_type == "transcript.text.delta":
                    delta = event.get("delta") or ""
                    if delta and first_delta_time is None:
                        first_delta_time = time.perf_counter()
                    if delta.strip():
                        delta_texts.append(delta)
                        if not args.no_stream and not args.json:
                            sys.stdout.write(delta)
                            sys.stdout.flush()
                elif event_type == "transcript.text.done":
                    final_text = (event.get("text") or "").strip()
                    usage = event.get("usage") or usage
                elif event_type == "error":
                    message = event.get("message") or json.dumps(
                        event, ensure_ascii=False
                    )
                    raise RuntimeError(f"SSE API error: {message}")

            if not final_text:
                final_text = "".join(delta_texts).strip()
            if not final_text:
                raise RuntimeError("SSE ASR did not return transcript text")

            first_delta_latency_ms = None
            if first_delta_time is not None:
                first_delta_latency_ms = (first_delta_time - send_time) * 1000

            return {
                "text": final_text,
                "language": args.language,
                "session_id": session_id,
                "first_delta_latency_ms": first_delta_latency_ms,
                "usage": usage,
            }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {exc.code}: {detail[:500]}")
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
        finally:
            if response is not None:
                response.close()

        if attempt >= max(1, args.max_retries) - 1:
            break
        time.sleep(args.retry_delay + attempt)

    raise RuntimeError(f"SSE ASR request failed: {last_error}")


def save_output(args, result):
    """Persist either plain text or JSON output when requested."""
    if not args.out:
        return

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.out, "w", encoding="utf-8") as handle:
        if args.json:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        else:
            handle.write(result["text"])

    print(f"Saved to: {args.out}", file=sys.stderr)


def validate_args(args):
    """Validate runtime configuration before sending the request."""
    if not args.api_url:
        print(
            "Error: custom ASR API URL is not configured. Set CUSTOM_ASR_API_URL "
            "(preferred), ASR_SSE_URL, or ASR_SSE_API_URL, or pass --api-url.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.api_key:
        print(
            "Error: custom ASR API key is not configured. Set CUSTOM_ASR_API_KEY "
            "(preferred), ASR_SSE_KEY, or ASR_SSE_API_KEY, or pass --api-key.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.model:
        print(
            "Error: custom ASR model is not configured. Set CUSTOM_ASR_MODEL "
            "(preferred) or ASR_SSE_MODEL, or pass --model.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not os.path.isfile(args.audio_file):
        print(f"Error: File not found: {args.audio_file}", file=sys.stderr)
        sys.exit(1)


def parse_args():
    """Parse CLI flags for the custom SSE ASR helper."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio via a custom streaming ASR API (HTTP SSE)."
    )
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument(
        "--api-url",
        default="",
        help="SSE ASR endpoint URL (default: CUSTOM_ASR_API_URL / ASR_SSE_URL)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Bearer token for the SSE ASR service (default: CUSTOM_ASR_API_KEY / ASR_SSE_KEY)",
    )
    parser.add_argument(
        "--model",
        default="",
        help="ASR model name (default: CUSTOM_ASR_MODEL)",
    )
    parser.add_argument(
        "--language",
        default="auto",
        help="Language code hint. Default: auto",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Prompt or system instruction sent to the transcription backend",
    )
    parser.add_argument(
        "--audio-type",
        "--format-type",
        dest="audio_type",
        default="",
        help="Audio type: wav, pcm, mp3, ogg, flac (auto-detected by extension)",
    )
    parser.add_argument(
        "--audio-codec",
        default="",
        help="Audio codec override; auto-detected when omitted",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Audio sample rate in Hz. Default: 16000",
    )
    parser.add_argument(
        "--audio-bits",
        type=int,
        default=16,
        help="Audio bits per sample. Default: 16",
    )
    parser.add_argument(
        "--audio-channel",
        type=int,
        default=1,
        help="Audio channel count. Default: 1",
    )
    parser.add_argument(
        "--vad-type",
        default="server_vad",
        help="VAD mode passed to the service. Default: server_vad",
    )
    parser.add_argument(
        "--silence-duration-ms",
        type=int,
        default=700,
        help="Silence duration threshold in ms. Default: 700",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=300,
        help="HTTP timeout in seconds. Default: 300",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of attempts. Default: 3",
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=2,
        help="Base retry delay in seconds. Default: 2",
    )
    parser.add_argument(
        "--user-id",
        default="",
        help="Optional X-User-Id header value",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Save transcription or JSON result to this file path",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming output, only print the final result",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON with metadata",
    )

    args = parser.parse_args()
    args.api_url = load_env_value(
        args.api_url,
        ("CUSTOM_ASR_API_URL", "ASR_SSE_URL", "ASR_SSE_API_URL"),
    )
    args.api_key = load_env_value(
        args.api_key,
        ("CUSTOM_ASR_API_KEY", "ASR_SSE_KEY", "ASR_SSE_API_KEY"),
    )
    args.model = load_env_value(args.model, ("CUSTOM_ASR_MODEL", "ASR_SSE_MODEL"))
    return args


def main():
    args = parse_args()
    validate_args(args)

    try:
        result = request_transcript(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if not args.no_stream and not args.json:
        print()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.no_stream:
        print(result["text"])

    save_output(args, result)


if __name__ == "__main__":
    main()
