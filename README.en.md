# ImgGen API

[简体中文](README.md) | English

ImgGen API lets Codex generate and edit images through a user-configured OpenAI-compatible Images API. It saves each result as a local file and then displays that file directly in Codex, without relying on chat-record recovery.

## Features

- Generate, edit, or batch-generate raster images.
- Use any compatible gateway that exposes the OpenAI Images API.
- Read the API base URL and Bearer credential from environment variables or the active Codex provider.
- Save outputs to explicit local paths for reliable display and reuse.
- Check connectivity and authentication without making a paid image request.
- Preview requests with `--dry-run`.

## Requirements

- Codex desktop or Codex CLI with the bundled `imagegen` skill.
- Python 3.8 or newer.
- An API provider that supports OpenAI-compatible image endpoints and Bearer-key authentication.

The gateway should expose `/v1/images/generations`. Image editing additionally requires `/v1/images/edits`. The optional `doctor` check uses `/v1/models`.

## Install in Codex

Ask Codex to install the skill from this repository:

```text
$skill-installer install the imggen-api skill from https://github.com/okiddo/imggen-api/tree/main/skills/imggen-api
```

Start a new Codex chat after installation. If the skill does not appear immediately, restart Codex.

## Configure a provider

Set the API base URL and Bearer key in your local environment. Do not paste API keys into a chat.

PowerShell:

```powershell
$env:IMAGEGEN_BASE_URL = "https://gateway.example.com/v1"
$env:IMAGEGEN_API_KEY = "your-api-key"
```

Bash:

```bash
export IMAGEGEN_BASE_URL="https://gateway.example.com/v1"
export IMAGEGEN_API_KEY="your-api-key"
```

These commands affect only the current shell and its child processes. For Codex desktop, launch Codex from that configured shell, or set persistent user environment variables and fully restart Codex.

`IMAGEGEN_BASE_URL` may be omitted when the active Codex provider already has a compatible `base_url`. The skill can also use that provider's configured `env_key`, or its matching Codex API-key cache when `requires_openai_auth = true`.

## Use in Codex

Generate an image:

```text
$imggen-api Generate a photorealistic tabby cat sitting beside a window at sunrise.
```

Generate with explicit options:

```text
$imggen-api Generate a 1536x1024 PNG product photo with gpt-image-2, medium quality, and save it under output/imagegen/.
```

Edit a local image:

```text
$imggen-api Edit D:\Images\source.png: replace the background with a clean white studio backdrop while preserving the subject.
```

Codex will call the configured API, verify the output, save it locally, and display the resulting image in the conversation.

## Diagnostics

From the installed skill directory:

```powershell
python scripts/imggen_api.py doctor
```

This checks the selected API base URL, Bearer authentication, and advertised models. It does not generate an image.

Preview a generation request without calling the image endpoint:

```powershell
python scripts/imggen_api.py generate --model gpt-image-2 --prompt "test" --size 1024x1024 --quality medium --output-format png --out "D:\output\test.png" --dry-run
```

## Compatibility scope

ImgGen API currently supports gateways that use the OpenAI-compatible Images API and `Authorization: Bearer <key>`. Gateways that require `X-API-Key`, command-generated tokens, custom request signing, or proprietary image endpoints need a separate adapter.

## Updating

`skill-installer` does not overwrite an existing skill directory. To update, rename the installed `imggen-api` directory as a backup, run the installation request again, and remove the backup after verifying the new version. Releases and version changes are recorded in [CHANGELOG.md](CHANGELOG.md).
