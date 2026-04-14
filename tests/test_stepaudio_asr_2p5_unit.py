#!/usr/bin/env python3
"""Unit tests for the stepaudio-asr-2p5 helper."""

import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "skills" / "stepaudio-asr-2p5" / "scripts" / "transcribe.py"

SPEC = importlib.util.spec_from_file_location("stepaudio_asr_2p5_transcribe", MODULE_PATH)
TRANSCRIBE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TRANSCRIBE)


class DetectFormatTests(unittest.TestCase):
    def test_detects_wav_defaults(self):
        self.assertEqual(
            TRANSCRIBE.detect_format("sample.wav", "", ""),
            ("wav", "pcm"),
        )

    def test_respects_codec_override(self):
        self.assertEqual(
            TRANSCRIBE.detect_format("sample.wav", "", "pcm_s16le"),
            ("wav", "pcm_s16le"),
        )

    def test_uses_explicit_type_with_default_codec(self):
        self.assertEqual(
            TRANSCRIBE.detect_format("sample.bin", "mp3", ""),
            ("mp3", "mp3"),
        )


class StreamParsingTests(unittest.TestCase):
    def test_decodes_multiple_json_objects_from_one_payload(self):
        payload = (
            '{"type":"transcript.text.delta","delta":"你"}'
            '{"type":"transcript.text.delta","delta":"好"}'
        )
        events = list(TRANSCRIBE.decode_json_stream(payload))
        self.assertEqual([event["delta"] for event in events], ["你", "好"])

    def test_parses_multiline_sse_events(self):
        response_lines = [
            b"event: message\n",
            b'data: {"type":"transcript.text.delta","delta":"hello"}\n',
            b"\n",
            b'data: {"type":"transcript.text.done","text":"hello"}\n',
            b"\n",
            b"data: [DONE]\n",
        ]
        events = list(TRANSCRIBE.iter_json_events(response_lines))
        self.assertEqual([event["type"] for event in events], [
            "transcript.text.delta",
            "transcript.text.done",
        ])


class EnvAliasTests(unittest.TestCase):
    def test_prefers_demo_env_aliases_for_url_and_key(self):
        argv = ["transcribe.py", "sample.wav"]
        env = {
            "ASR_SSE_URL": "https://example.com/v1/audio/asr/sse",
            "ASR_SSE_KEY": "demo-key",
            "ASR_SSE_MODEL": "step-asr-pt",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("sys.argv", argv):
                args = TRANSCRIBE.parse_args()
        self.assertEqual(args.api_url, env["ASR_SSE_URL"])
        self.assertEqual(args.api_key, env["ASR_SSE_KEY"])
        self.assertEqual(args.model, env["ASR_SSE_MODEL"])


if __name__ == "__main__":
    unittest.main()
