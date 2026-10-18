#!/usr/bin/env python3
"""Run ImgGen API against an OpenAI-compatible Images endpoint."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


SUPPORTED_COMMANDS = {"generate", "edit", "generate-batch"}
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    base_url: str
    env_key: str | None
    requires_openai_auth: bool


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser().resolve()

    installed_home = Path(__file__).resolve().parents[3]
    if (installed_home / "skills" / ".system" / "imagegen").is_dir():
        return installed_home
    return Path.home() / ".codex"


def load_toml(path: Path) -> dict[str, Any] | None:
    try:
        import tomllib
    except ImportError:
        return None
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, ValueError) as exc:
        raise AdapterError(f"Cannot read Codex config: {path}: {exc}") from exc
    return value if isinstance(value, dict) else {}


def strip_toml_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if quote == '"' and character == "\\":
            escaped = True
            continue
        if character in {'"', "'"}:
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
            continue
        if character == "#" and quote is None:
            return line[:index]
    return line


def parse_toml_string(value: str) -> str | None:
    value = value.strip()
    if len(value) < 2:
        return None
    if value.startswith('"') and value.endswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, str) else None
    if value.startswith("'") and value.endswith("'") and "'" not in value[1:-1]:
        return value[1:-1]
    return None


def parse_toml_bool(value: str) -> bool | None:
    if value.strip() == "true":
        return True
    if value.strip() == "false":
        return False
    return None


def provider_from_simple_toml(path: Path) -> ProviderConfig | None:
    """Read conventional provider fields when Python has no TOML parser.

    Ambiguous syntax is rejected so credentials are never routed based on a
    best-effort guess.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    active_provider: str | None = None
    provider_values: dict[str, dict[str, Any]] = {}
    current_provider: str | None = None
    in_root = True
    table_pattern = re.compile(
        r"^\[\s*model_providers\.(?P<provider>[A-Za-z0-9_-]+|\"(?:[^\"\\]|\\.)+\"|'[^']+')\s*\]$"
    )

    for raw_line in lines:
        line = strip_toml_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith("["):
            in_root = False
            match = table_pattern.fullmatch(line)
            if not match:
                current_provider = None
                continue
            token = match.group("provider")
            current_provider = (
                parse_toml_string(token) if token[:1] in {'"', "'"} else token
            )
            if current_provider:
                provider_values.setdefault(current_provider, {})
            continue
        if "=" not in line:
            continue
        key, raw_value = (part.strip() for part in line.split("=", 1))
        if in_root and key == "model_provider":
            active_provider = parse_toml_string(raw_value)
            continue
        if current_provider is None:
            continue
        if key in {"base_url", "env_key"}:
            parsed_string = parse_toml_string(raw_value)
            if parsed_string is not None:
                provider_values[current_provider][key] = parsed_string
        elif key == "requires_openai_auth":
            parsed_bool = parse_toml_bool(raw_value)
            if parsed_bool is not None:
                provider_values[current_provider][key] = parsed_bool

    values = provider_values.get(active_provider or "")
    if not active_provider or not isinstance(values, dict):
        return None
    configured_url = values.get("base_url")
    if not isinstance(configured_url, str):
        return None
    env_key = values.get("env_key")
    return ProviderConfig(
        provider_id=active_provider,
        base_url=configured_url,
        env_key=env_key if isinstance(env_key, str) else None,
        requires_openai_auth=values.get("requires_openai_auth") is True,
    )


def active_provider(home: Path) -> ProviderConfig | None:
    config_path = home / "config.toml"
    if not config_path.is_file():
        return None
    config = load_toml(config_path)
    if config is None:
        return provider_from_simple_toml(config_path)

    provider_id = config.get("model_provider")
    providers = config.get("model_providers")
    if not isinstance(provider_id, str) or not isinstance(providers, dict):
        return None
    provider = providers.get(provider_id)
    if not isinstance(provider, dict):
        return None
    configured_url = provider.get("base_url")
    if not isinstance(configured_url, str):
        return None
    env_key = provider.get("env_key")
    return ProviderConfig(
        provider_id=provider_id,
        base_url=configured_url,
        env_key=env_key if isinstance(env_key, str) else None,
        requires_openai_auth=provider.get("requires_openai_auth") is True,
    )


def normalized_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if not host:
        raise AdapterError("The image API base URL must include a hostname.")
    if parsed.username or parsed.password:
        raise AdapterError("Do not put credentials in IMAGEGEN_BASE_URL.")
    if parsed.query or parsed.fragment:
        raise AdapterError("IMAGEGEN_BASE_URL cannot include a query string or fragment.")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and host in LOOPBACK_HOSTS):
        raise AdapterError("Use HTTPS, except for loopback development URLs.")
    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def resolve_base_url(home: Path) -> tuple[str, str, ProviderConfig | None]:
    provider = active_provider(home)
    explicit = os.environ.get("IMAGEGEN_BASE_URL")
    if explicit and explicit.strip():
        return normalized_base_url(explicit), "IMAGEGEN_BASE_URL", provider
    if provider:
        return normalized_base_url(provider.base_url), "active Codex provider", provider
    raise AdapterError(
        "No image API base URL found. Configure an active Codex provider or set "
        "IMAGEGEN_BASE_URL to the provider's API root, including its path."
    )


def url_origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise AdapterError(f"Invalid port in image API base URL: {exc}") from exc
    scheme = parsed.scheme.lower()
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, (parsed.hostname or "").lower(), port


def matching_provider(provider: ProviderConfig | None, target_url: str) -> bool:
    if provider is None:
        return False
    return url_origin(normalized_base_url(provider.base_url)) == url_origin(target_url)


def cached_codex_key(home: Path) -> str | None:
    auth_path = home / "auth.json"
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = payload.get("OPENAI_API_KEY") if isinstance(payload, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve_api_key(
    home: Path, target_url: str, provider: ProviderConfig | None
) -> tuple[str, str]:
    explicit = os.environ.get("IMAGEGEN_API_KEY")
    if explicit and explicit.strip():
        return explicit.strip(), "IMAGEGEN_API_KEY"

    if matching_provider(provider, target_url):
        if provider and provider.env_key:
            configured = os.environ.get(provider.env_key)
            if configured and configured.strip():
                return configured.strip(), f"active provider env_key ({provider.env_key})"
        if provider and provider.requires_openai_auth:
            cached = cached_codex_key(home)
            if cached:
                return cached, "Codex API-key cache for matching active provider"

    expected = provider.env_key if matching_provider(provider, target_url) and provider else None
    hint = f" or set the configured provider variable {expected}" if expected else ""
    raise AdapterError(
        "No Bearer credential found. Set IMAGEGEN_API_KEY locally"
        f"{hint}, and never paste the key into chat."
    )


def bundled_imagegen(home: Path) -> Path:
    path = home / "skills" / ".system" / "imagegen" / "scripts" / "image_gen.py"
    if not path.is_file():
        raise AdapterError(f"Bundled imagegen CLI not found: {path}")
    return path


def model_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("data", payload.get("models", []))
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            value = item.get("id", item.get("slug"))
            if isinstance(value, str):
                result.append(value)
    return result


class SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if url_origin(req.full_url) != url_origin(newurl):
            raise HTTPError(
                req.full_url,
                code,
                "Refusing a cross-origin redirect while using a Bearer credential.",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def doctor(home: Path) -> int:
    api_base, base_source, provider = resolve_base_url(home)
    key, credential_source = resolve_api_key(home, api_base, provider)
    request = Request(
        f"{api_base}/models",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "imggen-api-skill/1.0",
        },
    )
    try:
        with build_opener(SameOriginRedirectHandler()).open(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise AdapterError(f"Gateway model check failed with HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AdapterError(f"Gateway model check failed: {exc}") from exc

    models = sorted(model_ids(payload))
    likely_images = [model for model in models if "image" in model.lower()]
    print(
        json.dumps(
            {
                "ok": True,
                "base_url": api_base,
                "base_url_source": base_source,
                "credential_source": credential_source,
                "advertised_model_count": len(models),
                "likely_image_models": likely_images,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    if not likely_images:
        print(
            "The gateway is reachable, but no model ID contains 'image'; a custom alias may still work.",
            file=sys.stderr,
        )
    return 0


def has_output_argument(arguments: list[str], command: str) -> bool:
    if command == "generate-batch":
        return "--out-dir" in arguments
    return "--out" in arguments or "--out-dir" in arguments


def run_imagegen(home: Path, arguments: list[str]) -> int:
    command = arguments[0]
    if command not in SUPPORTED_COMMANDS:
        raise AdapterError(
            f"Unknown command {command!r}; use generate, edit, generate-batch, or doctor."
        )
    if not has_output_argument(arguments, command):
        raise AdapterError("Pass an explicit --out or --out-dir so Codex can display the result.")

    api_base, _, provider = resolve_base_url(home)
    script = bundled_imagegen(home)
    child_env = os.environ.copy()
    child_env["OPENAI_BASE_URL"] = api_base
    if "--dry-run" not in arguments:
        key, _ = resolve_api_key(home, api_base, provider)
        child_env["OPENAI_API_KEY"] = key

    completed = subprocess.run(
        [sys.executable, str(script), *arguments],
        env=child_env,
        check=False,
    )
    return completed.returncode


def usage() -> str:
    return (
        "Usage:\n"
        "  imggen_api.py doctor\n"
        "  imggen_api.py generate [imagegen arguments] --out PATH\n"
        "  imggen_api.py edit [imagegen arguments] --out PATH\n"
        "  imggen_api.py generate-batch [imagegen arguments] --out-dir DIR"
    )


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments or arguments[0] in {"-h", "--help"}:
        print(usage())
        return 0
    home = codex_home()
    try:
        if arguments == ["doctor"]:
            return doctor(home)
        return run_imagegen(home, arguments)
    except AdapterError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
