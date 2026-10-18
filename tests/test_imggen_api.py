from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


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


if __name__ == "__main__":
    unittest.main()
