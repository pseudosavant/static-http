# Changelog

## 0.1.0

Initial release.

- Threaded static file server rooted at a user-selected directory.
- Dependency-free implementation.
- Byte-range support for `GET` and `HEAD` with `206` and `416` handling.
- `q` / `Q` interactive shutdown support.
- CLI options for bind address, port, directory, CORS, custom headers, directory listing policy, open browser, terminal QR display, cache policy, and verbosity controls.
- Range parser and HTTP behavior tests.
