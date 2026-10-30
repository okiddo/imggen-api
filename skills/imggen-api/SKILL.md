---
name: imggen-api
description: Generate or edit raster images through a user-configured OpenAI-compatible Images API, save outputs locally, and display them in Codex. Use when the user invokes $imggen-api or when a custom provider exposes the Images API but Codex's hosted generator is unavailable. Requires Bearer-key authentication; do not use for proprietary image endpoints.
---

# ImgGen API

Use a custom provider's direct Images API when Codex's hosted `image_gen` tool
is unavailable. The adapter writes outputs to disk, so the saved file is the
source of truth. Do not scan task JSONL or use image-recovery workflows for
these outputs.

## Adapter

Run `scripts/imggen_api.py`. It delegates generation and editing
to Codex's bundled `imagegen/scripts/image_gen.py` instead of duplicating the
image client.

The API base URL is selected in this order:

1. `IMAGEGEN_BASE_URL`.
2. The active Codex provider's `base_url` in `config.toml`.

Include the API path in the URL, such as `https://gateway.example.com/v1`.
For compatibility, a URL with no path is normalized to `/v1`; an existing path
is preserved.

The Bearer credential is selected in this order:

1. `IMAGEGEN_API_KEY`.
2. The active provider's configured `env_key`, but only when its origin matches
   the selected API base URL.
3. The active Codex configuration's `experimental_bearer_token`, used by CC
   Switch imports, under the same origin restriction.
4. The Codex API-key cache when the matching active provider uses
   `requires_openai_auth = true`.

Never ask users to paste a key into chat. Ask them to set the applicable local
environment variable. The adapter never modifies `config.toml`, `auth.json`, or
persistent environment variables and never prints credential values.

## Workflow

1. When connectivity or model discovery is unknown, run the no-generation
   check once:

   ```powershell
   python scripts/imggen_api.py doctor
   ```

   A successful `/models` response verifies authentication and connectivity,
   not that a particular model supports image generation. Custom aliases may
   not contain the word `image`.

2. Generate one requested image and provide an explicit, non-existing output
   path under the workspace's `output/imagegen/`:

   ```powershell
   python scripts/imggen_api.py generate --model gpt-image-2 --prompt "<prompt>" --quality medium --size 1024x1024 --output-format png --out "<absolute-output-path>"
   ```

3. For an edit, pass local input paths through the bundled CLI:

   ```powershell
   python scripts/imggen_api.py edit --model gpt-image-2 --image "<absolute-input-path>" --prompt "<edit instructions and invariants>" --out "<absolute-output-path>"
   ```

4. After a successful call, verify every expected output exists and is a
   readable image. Inspect a single output with `view_image`. Report its actual
   format, dimensions, byte size, and SHA-256 when available.

5. Display the result using its exact absolute path:

   ```markdown
   ![Generated image](<absolute/path/to/output.png>)

   [Open image](<absolute/path/to/output.png>)
   ```

## Constraints

- A user's image request authorizes only the requested number of paid calls.
  Do not make an extra generation to test a provider.
- Keep the user's requested model. Otherwise default to `gpt-image-2`; never
  silently switch models after an API error.
- Use `--dry-run` to inspect a request without an API call.
- Require HTTPS except for loopback development URLs. Reject URL credentials,
  query strings, and fragments.
- This adapter supports Bearer-key authentication only. Do not claim support
  for `env_http_headers`, command-backed auth, or proprietary image endpoints.
- If the provider returns dimensions or metadata different from the request,
  report the verified result rather than claiming exact conformance.
- `[features].image_generation = true` does not route a custom provider through
  Codex's hosted tool. This Skill intentionally uses the direct Images API.
