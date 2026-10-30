# Changelog

All notable changes to ImgGen API will be documented in this file.

## 0.1.2

- Recognize CC Switch-imported `experimental_bearer_token` credentials from the active Codex configuration.
- Apply the existing provider-origin check before forwarding imported credentials.
- Preserve environment-variable precedence and the existing `auth.json` fallback.
- Add regression tests for standard and fallback TOML parsing, credential priority, origin isolation, cache fallback, and diagnostic redaction.

## 0.1.1

- Make Simplified Chinese the default README and keep the English guide in `README.en.md`.
- Update repository links for the new GitHub account.
- Clarify desktop environment-variable setup and the non-overwriting update process.
- Accept `--out=PATH` and `--out-dir=DIR` argument forms.
- Add offline unit tests for URL validation, model parsing, and output arguments.

## 0.1.0

- Initial public release.
- Generate, edit, and batch-generate images through an OpenAI-compatible Images API.
- Save generated files locally and display them in Codex.
- Support Bearer-key authentication, provider discovery, diagnostics, and dry runs.

