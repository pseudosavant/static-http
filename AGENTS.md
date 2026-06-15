# AGENTS.md

Guidance for future automated development on this repository.

## Project identity

- PyPI project name: `static-http`
- GitHub repository name: `static-http`
- Console command: `static-http`
- Import package: `http_here`
- Runtime dependency policy: no runtime dependencies
- Supported Python: `>=3.10`
- License: MIT, copyright John Paul Ellis

The repository path may still be named `http-here` locally for historical reasons. Do not rename the Python import package from `http_here` unless the user explicitly asks for a breaking internal package rename.

## Product intent

`static-http` is a small temporary static file server for local development, file transfer, media playback, and archive inspection workflows. It is not a production web server.

Preserve these core behaviors:

- Serve the current working directory by default.
- Bind to `0.0.0.0` by default.
- Listen on port `8080` by default.
- Support `GET`, `HEAD`, and single byte-range requests.
- Reject multipart ranges instead of returning invalid partial support.
- Hide dot-prefixed and platform-hidden files/directories by default.
- Expose hidden files only with `--include-hidden`.
- Suppress per-request logs by default.
- Print request logs only with `--verbose`.
- Keep startup/shutdown output visible even when request logs are quiet.
- Quit on `q` or `Q`; Ctrl+C should also shut down cleanly.
- Keep `--open` preferring localhost when bound to all interfaces.
- Keep `--qr` preferring a discovered LAN URL when bound to all interfaces.

Do not add upload support, authentication, TLS, dynamic app-server behavior, or remote shutdown endpoints unless the user explicitly changes the project scope.

## Implementation notes

- Main CLI lifecycle: `src/http_here/cli.py`
- Static server/path/range HTTP behavior: `src/http_here/server.py`
- Range parsing: `src/http_here/ranges.py`
- Terminal QR renderer: `src/http_here/qrcode.py`
- URL discovery/selection: `src/http_here/urls.py`
- Keyboard shutdown handling: `src/http_here/keyboard.py`

The QR renderer is intentionally dependency-free and currently supports QR versions 1-4 at error correction level L in byte mode. The payload limit is 78 UTF-8 bytes. That is sufficient for normal localhost, IPv4 LAN, and expanded IPv6 root URLs. If longer URLs become necessary, expand the QR implementation deliberately and add decode tests.

Path handling is security-sensitive. Preserve root confinement for direct paths, encoded traversal attempts, Windows-style separators, symlinks, junctions, and auto-served directory indexes.

HTTP conditional handling should use HTTP-date second precision, not filesystem sub-second precision.

Custom response headers should apply consistently, including normal file responses, directory listings, redirects, range errors, and HTTP error responses.

## Development commands

Use `uv` for local development:

```powershell
uv sync --extra dev
uv run pytest
uv run python -m build
uv run python -m twine check dist/*
```

Useful focused tests:

```powershell
uv run pytest tests/test_ranges.py
uv run pytest tests/test_server.py
uv run pytest tests/test_qrcode.py
uv run pytest tests/test_cli.py
```

When pytest cache writes fail on Windows/OneDrive, use:

```powershell
uv run pytest -p no:cacheprovider --basetemp .pytest-tmp
```

Clean generated build/test artifacts before committing:

- `build/`
- `dist/`
- `*.egg-info/`
- `.pytest_cache/`
- `.pytest-tmp/`
- `__pycache__/`

Never commit `.venv/`, generated distributions, pytest cache, bytecode, or manual smoke-test output.

## Release process

For a versioned release:

1. Update `pyproject.toml`.
2. Update `src/http_here/__init__.py`.
3. Update `CHANGELOG.md`.
4. Run tests and build/metadata checks when requested or before publishing.
5. Commit with a release message such as `Release 1.0.1`.
6. Tag with `vX.Y.Z`.
7. Push `main` and the tag.

The trusted publishing workflow is `.github/workflows/release.yml`, and the PyPI environment name is `pypi`.

## Documentation expectations

Keep README examples aligned with the published package and command name `static-http`.

The README should continue to document:

- `uvx static-http`
- `pipx run static-http`
- `python -m pip install static-http`
- default bind/port behavior
- byte-range examples
- hidden-file defaults and `--include-hidden`
- QR behavior and practical limitations
- shutdown behavior
- security warning for `0.0.0.0`, no auth, and trusted-network use

## Compatibility expectations

CI should cover Windows, macOS, and Linux across supported Python versions. Be careful with changes involving:

- terminal keyboard handling
- Windows hidden file attributes
- symlink/junction behavior
- path separators and URL decoding
- socket binding and LAN URL discovery
- terminal ANSI output
