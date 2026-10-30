from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "imggen-api"
    / "scripts"
    / "imggen_api.py"
)
SPEC = importlib.util.spec_from_file_location("imggen_api", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {SCRIPT}")
imggen_api = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = imggen_api
SPEC.loader.exec_module(imggen_api)


class NormalizeBaseUrlTests(unittest.TestCase):
    def test_adds_default_v1_path(self) -> None:
        self.assertEqual(
            imggen_api.normalized_base_url("https://gateway.example.com/"),
            "https://gateway.example.com/v1",
        )

    def test_preserves_custom_path(self) -> None:
        self.assertEqual(
            imggen_api.normalized_base_url("https://gateway.example.com/api/openai/"),
            "https://gateway.example.com/api/openai",
        )

    def test_rejects_plain_http_for_remote_hosts(self) -> None:
        with self.assertRaises(imggen_api.AdapterError):
            imggen_api.normalized_base_url("http://gateway.example.com/v1")

    def test_allows_plain_http_for_loopback(self) -> None:
        self.assertEqual(
            imggen_api.normalized_base_url("http://localhost:8080/v1"),
            "http://localhost:8080/v1",
        )

    def test_rejects_credentials_query_and_fragment(self) -> None:
        invalid_urls = (
            "https://user:secret@gateway.example.com/v1",
            "https://gateway.example.com/v1?token=secret",
            "https://gateway.example.com/v1#fragment",
        )
        for value in invalid_urls:
            with self.subTest(value=value), self.assertRaises(imggen_api.AdapterError):
                imggen_api.normalized_base_url(value)


class ArgumentTests(unittest.TestCase):
    def test_accepts_split_output_arguments(self) -> None:
        self.assertTrue(imggen_api.has_output_argument(["generate", "--out", "a.png"], "generate"))
        self.assertTrue(
            imggen_api.has_output_argument(
                ["generate-batch", "--out-dir", "images"], "generate-batch"
            )
        )

    def test_accepts_equals_output_arguments(self) -> None:
        self.assertTrue(imggen_api.has_output_argument(["generate", "--out=a.png"], "generate"))
        self.assertTrue(
            imggen_api.has_output_argument(
                ["generate-batch", "--out-dir=images"], "generate-batch"
            )
        )

    def test_batch_requires_output_directory(self) -> None:
        self.assertFalse(
            imggen_api.has_output_argument(
                ["generate-batch", "--out=image.png"], "generate-batch"
            )
        )


class ModelIdsTests(unittest.TestCase):
    def test_reads_openai_data_shape(self) -> None:
        self.assertEqual(
            imggen_api.model_ids({"data": [{"id": "gpt-image-2"}]}),
            ["gpt-image-2"],
        )

    def test_reads_alternate_models_shape(self) -> None:
        self.assertEqual(
            imggen_api.model_ids({"models": [{"slug": "image-alias"}]}),
            ["image-alias"],
        )


class CredentialResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = Path(self.temp_dir.name)

    def write_config(
        self,
        *,
        token: str = "cc-switch-secret",
        env_key: str | None = None,
        requires_openai_auth: bool = False,
    ) -> None:
        env_line = f'env_key = "{env_key}"\n' if env_key else ""
        auth_line = "requires_openai_auth = true\n" if requires_openai_auth else ""
        (self.home / "config.toml").write_text(
            f'''experimental_bearer_token = "{token}"
model_provider = "custom"

[model_providers.custom]
base_url = "https://gateway.example.com/v1"
{env_line}{auth_line}''',
            encoding="utf-8",
        )

    def test_reads_cc_switch_bearer_token_for_matching_provider(self) -> None:
        self.write_config()
        provider = imggen_api.active_provider(self.home)
        with patch.dict(os.environ, {}, clear=True):
            key, source = imggen_api.resolve_api_key(
                self.home, "https://gateway.example.com/v1", provider
            )
        self.assertEqual(key, "cc-switch-secret")
        self.assertEqual(source, "active Codex config experimental_bearer_token")

    def test_explicit_and_provider_environment_keys_keep_priority(self) -> None:
        self.write_config(env_key="CUSTOM_IMAGE_KEY")
        provider = imggen_api.active_provider(self.home)
        with patch.dict(
            os.environ,
            {"IMAGEGEN_API_KEY": "explicit-secret", "CUSTOM_IMAGE_KEY": "env-secret"},
            clear=True,
        ):
            self.assertEqual(
                imggen_api.resolve_api_key(
                    self.home, "https://gateway.example.com/v1", provider
                ),
                ("explicit-secret", "IMAGEGEN_API_KEY"),
            )
        with patch.dict(os.environ, {"CUSTOM_IMAGE_KEY": "env-secret"}, clear=True):
            self.assertEqual(
                imggen_api.resolve_api_key(
                    self.home, "https://gateway.example.com/v1", provider
                ),
                ("env-secret", "active provider env_key (CUSTOM_IMAGE_KEY)"),
            )

    def test_rejects_cc_switch_token_for_different_origin(self) -> None:
        self.write_config()
        provider = imggen_api.active_provider(self.home)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(
            imggen_api.AdapterError
        ):
            imggen_api.resolve_api_key(
                self.home, "https://other.example.com/v1", provider
            )

    def test_empty_cc_switch_token_falls_back_to_auth_cache(self) -> None:
        self.write_config(token="   ", requires_openai_auth=True)
        (self.home / "auth.json").write_text(
            json.dumps({"OPENAI_API_KEY": "cached-secret"}), encoding="utf-8"
        )
        provider = imggen_api.active_provider(self.home)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                imggen_api.resolve_api_key(
                    self.home, "https://gateway.example.com/v1", provider
                ),
                ("cached-secret", "Codex API-key cache for matching active provider"),
            )

    def test_simple_toml_fallback_reads_cc_switch_token(self) -> None:
        self.write_config()
        with patch.object(imggen_api, "load_toml", return_value=None):
            provider = imggen_api.active_provider(self.home)
        self.assertIsNotNone(provider)
        self.assertEqual(provider.experimental_bearer_token, "cc-switch-secret")

    def test_doctor_reports_source_without_printing_secret(self) -> None:
        self.write_config()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"data":[{"id":"gpt-image-2"}]}'

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse()

        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(
            imggen_api, "build_opener", return_value=FakeOpener()
        ), contextlib.redirect_stdout(output):
            self.assertEqual(imggen_api.doctor(self.home), 0)
        self.assertIn("active Codex config experimental_bearer_token", output.getvalue())
        self.assertNotIn("cc-switch-secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
