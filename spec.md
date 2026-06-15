# static-http Specification

## Purpose

`static-http` is a small, dependency-free Python command-line tool for starting a temporary static HTTP server rooted at the current working directory, with correct byte-range request support.

It is intended to be the command you can run from any folder when a browser, media player, installer, archive reader, or other client needs files over HTTP:

```powershell
uvx static-http
```

The project should prioritize predictable temporary-server behavior, modern Python compatibility, and a clean CLI over framework-style configurability.

## Goals

- Serve static files from the current directory by default.
- Support HTTP byte-range requests, including `Range: bytes=start-end`, open-ended ranges, and suffix ranges.
- Work well with `uvx static-http` without extra arguments.
- Be dependency-free at runtime.
- Provide a clean interactive shutdown key: pressing `q` or `Q` in the focused terminal quits the server.
- Be robust enough for common local-development, file-transfer, media, and archive-inspection workflows.
- Be explicit that it is a temporary development/file-serving tool, not a production web server.

## Non-Goals

- No dynamic application server features.
- No upload support in v1.
- No built-in authentication in v1 unless later justified by real usage.
- No remote HTTP quit endpoint.
- No TLS in v1 unless later added as a clearly optional feature.
- No directory write access or file modification features.

## Package And Command

- PyPI project name: `static-http`
- Repository name: `static-http`
- Import package name: `http_here`
- Console script: `static-http`

`pyproject.toml` should define:

```toml
[project.scripts]
static-http = "http_here.cli:main"
```

Minimum supported Python version should be `>=3.9` unless implementation details make `>=3.10` more practical. Runtime dependencies should be empty.

## Default Behavior

Running:

```powershell
static-http
```

must:

- Serve the current working directory.
- Bind to all interfaces by default: `0.0.0.0`.
- Listen on port `8080`.
- Use a threaded HTTP server so multiple clients and browser preconnects do not block each other.
- Print the effective listening URL and root directory.
- Print a clear quit hint immediately after startup.
- Continue serving until `q`, `Q`, Ctrl+C, or process termination.

Example startup output:

```text
Serving C:\Users\paul\Downloads at:
  http://0.0.0.0:8080/
  http://localhost:8080/

Press Q to quit.
```

If bound to `0.0.0.0`, the tool should also print the localhost URL. If LAN URLs can be discovered reliably, they should be printed as well, especially when `--verbose` or `--qr` is used.

## CLI

### Positional Arguments

`static-http` should not accept positional arguments in v1. All configuration should be explicit options.

### Options

```text
-p, --port PORT
```

Port to listen on. Default: `8080`.

Rules:

- `--port 0` asks the OS to assign an ephemeral free port.
- When `--port 0` is used, startup output must print the actual assigned port from the server socket.
- Invalid port values should fail during argument parsing with exit code `2`.

```text
-d, --directory PATH
```

Directory to serve. Default: current directory.

```text
-b, --bind ADDRESS
```

Address to bind. Default: `0.0.0.0`.

```text
--localhost-only
```

Shortcut for binding to `127.0.0.1`.

Rules:

- `--localhost-only` and `--bind` are mutually exclusive.
- `--localhost-only` must bind IPv4 localhost, `127.0.0.1`, not all interfaces.
- If IPv6 localhost support is later added, it should be explicit.

```text
--cors
```

Enable permissive CORS by adding:

```text
Access-Control-Allow-Origin: *
```

This is intended for temporary browser-based workflows that require cross-origin file access.

```text
--header "Name: Value"
```

Optional repeatable response header for advanced temporary use cases.

Examples:

```powershell
static-http --header "Cross-Origin-Opener-Policy: same-origin"
static-http --header "Cache-Control: no-store"
```

Validation:

- Header names must be non-empty.
- Header values must not contain CR or LF.
- Header names must not contain `:` after parsing.

`--cors` is equivalent to a built-in `Access-Control-Allow-Origin: *` header and should compose with `--header`.

```text
--no-dir-list
```

Disable generated directory listings. If a directory lacks an index file, return `403 Forbidden`.

Default should allow directory listings, matching `http.server`.

```text
--version
```

Print package version and exit.

### Additional Required Options

```text
--open
```

Open the server URL in the default browser after startup.

Behavior:

- Prefer the localhost URL when bound to all interfaces.
- Prefer the actual bound URL when `--localhost-only` or `--bind` is used.
- If opening the browser fails, keep the server running and print a warning.

`--port 0` must support OS-assigned ephemeral ports.

```powershell
static-http --port 0
```

The startup output must print the actual assigned port from the server socket.

```text
--qr
```

Print a QR code for a useful server URL.

Requirements:

- Must not add runtime dependencies.
- Use a built-in terminal QR renderer.
- When bound to all interfaces, prefer a discovered LAN URL if one can be determined.
- If no LAN URL can be determined, fall back to the localhost URL.
- If the terminal is too narrow for a QR code, print a clear warning and keep serving.
- QR output should be optional and only printed when `--qr` is passed.

```text
--no-cache
```

Shortcut for `Cache-Control: no-store`.

This should compose with `--header`. If the user also supplies an explicit `Cache-Control` header, the explicit header should win.

```text
--quiet
```

Suppress per-request logs while keeping startup and shutdown messages. This is the default behavior; the flag exists to make the choice explicit.

```text
--verbose
```

Print request logs and extra binding/debug information.

`--quiet` and `--verbose` are mutually exclusive.

## HTTP Semantics

The server should subclass or adapt `http.server.SimpleHTTPRequestHandler` and implement range-aware static responses without external dependencies.

### Methods

Required:

- `GET`
- `HEAD`

Inherited behavior for unsupported methods should remain standard and return appropriate errors.

### File Serving

For normal file requests without `Range`:

- Return `200 OK`.
- Include accurate `Content-Length`.
- Include `Content-Type`.
- Include `Last-Modified`.
- Include `Accept-Ranges: bytes`.
- Preserve standard conditional request behavior where practical, especially `If-Modified-Since`.

For `HEAD`, return the same headers that `GET` would return, without a response body.

### Range Requests

The server must support:

```text
Range: bytes=0-99
Range: bytes=100-
Range: bytes=-500
```

For a satisfiable single range:

- Return `206 Partial Content`.
- Include `Content-Range: bytes START-END/TOTAL`.
- Include `Content-Length` equal to the selected byte count.
- Include `Accept-Ranges: bytes`.
- Send only the selected byte range.

For an unsatisfiable range:

- Return `416 Range Not Satisfiable`.
- Include `Content-Range: bytes */TOTAL`.
- Do not send file content.

For syntactically invalid ranges:

- Prefer `400 Bad Request` with a concise error.
- Do not send file content.

### Multiple Ranges

V1 may choose one of two approaches:

1. Fully support multipart byte ranges.
2. Reject multiple ranges with `400 Bad Request`.

Recommendation for v1: reject multiple ranges explicitly with `400 Bad Request`.

Reasoning: the dominant temporary-server use cases need single ranges. Multipart range responses are more complex to implement and test correctly. A clear rejection is safer than a partial or subtly invalid implementation.

This can be revisited later.

### If-Range

V1 may ignore `If-Range` and serve according to normal `Range` behavior, but this should be documented as a known limitation.

If implemented, it should be tested carefully with `Last-Modified` and future `ETag` support.

### Content Encoding

The server should serve files as stored and should not apply compression. This avoids ambiguous byte ranges over compressed transfer encodings.

## Path Handling And Security

The server must be rooted to the selected directory.

Requirements:

- Resolve `--directory` to an absolute path during startup.
- Fail fast if the directory does not exist or is not a directory.
- URL paths must not escape the root directory.
- Ignore or reject path traversal segments such as `..`.
- Decode URL paths safely.
- Handle Windows path separators correctly.
- Never map a request to a drive root or absolute path supplied in the URL.
- Preserve standard behavior for `index.html` and `index.htm`.

The implementation should avoid global CWD changes where practical by using the `directory` support in `SimpleHTTPRequestHandler` or an equivalent explicit root mapping.

## Interactive Shutdown

`static-http` must support quitting by pressing `q` or `Q` while the terminal window has focus.

Startup output must include:

```text
Press Q to quit.
```

Behavior:

- Pressing `q` or `Q` initiates graceful shutdown.
- Ctrl+C should also initiate graceful shutdown.
- On shutdown, stop accepting new connections.
- Allow active request handlers to complete briefly if practical.
- Print a concise shutdown message, for example:

```text
Shutting down.
```

Implementation guidance:

- Run the HTTP server in a background thread.
- The main thread should monitor keyboard input.
- On Windows, use `msvcrt.getwch()` or equivalent for single-key input without requiring Enter.
- On POSIX terminals, use `termios`/`tty` to read one character without requiring Enter, restoring terminal settings on exit.
- If raw single-key input cannot be enabled, fall back to line input where entering `q` then Enter quits, and print a warning that Enter is required.

There must be no HTTP endpoint that shuts down the server.

## Logging

Default logging should be useful but not noisy.

Required behavior:

- Print startup information to stdout.
- Print shutdown information to stdout.
- Suppress per-request logs by default.

When `--quiet` is used:

- Suppress per-request logs.
- Do not suppress startup errors.

When `--verbose` is used:

- Print per-request logs.
- Print the resolved root directory.
- Print the resolved bind address and actual port.
- Print any discovered LAN URLs.
- Print warning details for non-fatal startup conveniences such as browser-open or QR rendering failures.

`--quiet` and `--verbose` must be mutually exclusive.

## Error Handling

Startup errors should be direct and actionable:

- Directory missing.
- Directory is not a directory.
- Port already in use.
- Permission denied binding port.
- Invalid port.
- Invalid bind address.
- Mutually exclusive options used together.

Examples:

```text
Directory does not exist: C:\missing
Could not bind 0.0.0.0:8080: address already in use
```

Exit codes:

- `0`: normal shutdown.
- `2`: CLI usage error.
- `1`: runtime startup error.

## Project Structure

Recommended layout:

```text
static-http/
  pyproject.toml
  README.md
  LICENSE
  CHANGELOG.md
  src/
    http_here/
      __init__.py
      __main__.py
      cli.py
      server.py
      ranges.py
      keyboard.py
      urls.py
      qrcode.py
  tests/
    test_cli.py
    test_ranges.py
    test_server.py
    test_paths.py
    test_keyboard.py
  .github/
    workflows/
      ci.yml
      publish.yml
```

### Module Responsibilities

`http_here.cli`

- Argument parsing.
- Startup output.
- Server lifecycle coordination.
- Exit code handling.

`http_here.server`

- Threading HTTP server subclass.
- Static request handler.
- CORS/custom header handling.
- Directory listing control.

`http_here.ranges`

- Parse `Range` headers.
- Normalize ranges against file sizes.
- Produce `Content-Range` values.
- Keep range logic isolated and heavily tested.

`http_here.keyboard`

- Cross-platform `q`/`Q` key monitoring.
- Fallback behavior when raw key reads are unavailable.

`http_here.urls`

- Compute display URLs.
- Resolve actual socket host and port.
- Discover likely LAN URLs without runtime dependencies.
- Choose the preferred URL for `--open` and `--qr`.

`http_here.qrcode`

- Render terminal QR codes without runtime dependencies.
- Keep QR implementation isolated and tested.
- Report when terminal dimensions are too small.

## Testing Requirements

Tests should use only the standard library unless development dependencies are added for test ergonomics.

Recommended test runner: `pytest`, as a development dependency only.

### Unit Tests

Range parser:

- `bytes=0-99`
- `bytes=100-`
- `bytes=-500`
- `bytes=0-0`
- range ending past EOF clamps correctly
- start beyond EOF is unsatisfiable
- empty range is invalid
- non-byte unit is invalid
- multiple ranges are rejected in v1
- malformed numeric values are invalid

Path handling:

- normal nested file lookup
- URL-encoded filenames
- traversal attempts do not escape root
- Windows-style separators in URLs do not escape root

CLI:

- default port is `8080`
- default bind is `0.0.0.0`
- `--port 0` is accepted and reports the actual assigned port
- positional ports are rejected
- `--localhost-only` maps to `127.0.0.1`
- `--localhost-only` conflicts with `--bind`
- `--cors` sets expected header
- `--no-cache` sets `Cache-Control: no-store`
- explicit `--header "Cache-Control: ..."` wins over `--no-cache`
- `--quiet` conflicts with `--verbose`
- `--open` selects the expected browser URL
- `--qr` selects the expected QR URL
- invalid directory fails

QR renderer:

- renders a known URL as terminal output without dependencies
- reports a too-narrow terminal without crashing
- does not emit QR output unless `--qr` is passed

### Integration Tests

Start the server on port `0` with a temporary directory, then use standard-library HTTP clients to verify:

- startup reports the actual assigned port.
- full `GET` returns `200` and full file.
- `HEAD` returns headers and no body.
- range `GET` returns `206` and exact bytes.
- suffix range returns expected bytes.
- unsatisfiable range returns `416`.
- CORS header appears when enabled.
- custom headers appear when configured.
- `--no-cache` adds `Cache-Control: no-store`.
- directory listing works by default.
- directory listing can be disabled with `--no-dir-list`.
- `--quiet` suppresses request logs.
- `--verbose` prints extra bind/URL details.

### Manual Smoke Tests

Before publishing:

```powershell
uvx --from . static-http
uvx --from . static-http --localhost-only
uvx --from . static-http --port 9000 --cors
uvx --from . static-http --port 0
uvx --from . static-http --directory C:\Temp
uvx --from . static-http --open
uvx --from . static-http --qr
uvx --from . static-http --no-cache
uvx --from . static-http --quiet
uvx --from . static-http --verbose
```

Verify:

- Browser can load files.
- `static-http --port 0` prints the actual assigned port.
- `--open` launches the preferred URL.
- `--qr` prints a scannable terminal QR code or a clear terminal-size warning.
- A range-aware client receives `206`.
- Pressing `Q` quits without Ctrl+C.
- Ctrl+C still quits cleanly.

## CI

GitHub Actions should run on:

- Windows
- macOS
- Ubuntu

Python versions:

- Oldest supported version
- Latest stable version

CI steps:

- install with development dependencies
- run tests
- build package
- inspect metadata

Suggested tooling:

```text
python -m pip install -e ".[dev]"
python -m pytest
python -m build
python -m twine check dist/*
```

## Publishing

Use a trusted publishing workflow from GitHub Actions to PyPI.

Release process:

1. Update `CHANGELOG.md`.
2. Bump version.
3. Tag release, for example `v0.1.0`.
4. GitHub Actions builds sdist and wheel.
5. Publish to PyPI via trusted publishing.

Initial release should be `0.1.0`.

## README Requirements

The README should include:

- What `static-http` does.
- Why it exists: `python -m http.server` does not support range requests.
- Quick start with `uvx static-http`.
- Install examples:

```powershell
uvx static-http
pipx run static-http
python -m pip install static-http
static-http
```

- CLI reference.
- `--open`, `--qr`, `--no-cache`, `--quiet`, and `--verbose` examples.
- Range support examples using `curl`.
- Shutdown behavior: press `Q`.
- Security note: temporary server, not production.
- License.

## License

Recommended license: MIT or Apache-2.0.

MIT is simpler for a small utility. Apache-2.0 is also reasonable if patent language is desired.

## Open Design Questions

- Should the package support Python 3.9, or start at 3.10/3.11 for simpler typing and maintenance?
- Should multipart ranges be implemented later, or permanently out of scope?
- Should default startup output always print discovered LAN URLs, or reserve them for `--verbose` and `--qr`?

## V1 Acceptance Criteria

The initial PyPI release is ready when:

- `uvx static-http` starts a server rooted at the current directory.
- Default bind is `0.0.0.0`.
- Default port is `8080`.
- `--port 0` works and startup output reports the actual assigned port.
- Positional port arguments are rejected.
- `--localhost-only` binds to `127.0.0.1`.
- `--directory`, `--bind`, `--cors`, `--header`, `--no-dir-list`, `--open`, `--qr`, `--no-cache`, `--quiet`, and `--verbose` work.
- `--quiet` suppresses request logs.
- `--verbose` prints extra bind and URL details.
- `--qr` prints a terminal QR code without runtime dependencies.
- Single byte-range requests return correct `206` responses.
- Unsatisfiable ranges return correct `416` responses.
- Path traversal attempts cannot escape the root.
- Pressing `q` or `Q` in the focused terminal shuts the server down cleanly.
- Ctrl+C shuts the server down cleanly.
- The package has no runtime dependencies.
- Tests pass on Windows, macOS, and Linux.
- README documents usage, shutdown, and security limitations.
