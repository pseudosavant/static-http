# static-http

`static-http` is a tiny dependency-free Python utility that starts a temporary static HTTP server in the current directory with byte-range support for quick local workflows.

It is intentionally focused on temporary file serving for local development, manual testing, media playback, and archive inspection.

## Why this exists

`python -m http.server` is excellent for quick sharing but does not implement byte-range request handling. `static-http` fills that gap with a small CLI that keeps the behavior predictable and easy to reason about.

## Install

```powershell
uvx static-http
pipx run static-http
python -m pip install static-http
```

## Quick start

```powershell
static-http
```

```powershell
uvx static-http
```

By default:

- Serves the current working directory.
- Binds to `0.0.0.0`.
- Listens on port `8080`.
- Uses a threaded HTTP server.
- Handles `GET`, `HEAD`, and single-range requests.

## CLI

`static-http` supports these options:

- `-p, --port PORT` — listening port. `0` requests an OS-assigned port.
- `-d, --directory PATH` — root directory to serve. Default is the current directory.
- `-b, --bind ADDRESS` — bind address. Default is `0.0.0.0`.
- `--localhost-only` — equivalent to `--bind 127.0.0.1`.
- `--cors` — adds `Access-Control-Allow-Origin: *`.
- `--header "Name: Value"` — repeatable custom headers.
- `--no-dir-list` — disable directory listing responses when no index file exists.
- `--open` — open the server URL in the default browser after startup.
- `--qr` — render a terminal QR code for the server URL.
- `--no-cache` — send `Cache-Control: no-store`.
- `--quiet` — suppress per-request logs.
- `--verbose` — print detailed startup/binding information.
- `--include-hidden` — include dot-prefixed files and directories in normal serving and directory listings.
- `--version` — print package version and exit.

## Examples

```powershell
static-http --open
static-http --qr
static-http --no-cache
static-http --quiet
static-http --verbose
static-http --include-hidden
static-http --port 9000 --cors
static-http --no-dir-list
```

## Shutdown

Press `Q` or `q` in the focused terminal to stop the server. `Ctrl+C` also triggers a graceful shutdown.

## Range support

`GET` requests support single byte ranges with examples:

```bash
curl -H "Range: bytes=0-99" http://localhost:8080/video.mp4 -o part.bin
curl -H "Range: bytes=100-" http://localhost:8080/video.mp4 -o tail.bin
curl -H "Range: bytes=-500" http://localhost:8080/video.mp4 -o suffix.bin
```

The server returns `206 Partial Content` for satisfiable ranges, `416 Range Not Satisfiable` when the range is outside the file, and `400 Bad Request` for invalid range syntax.

## Security note

`static-http` is intentionally a **temporary** local development/file-serving tool, not a production web server.

## License

MIT
