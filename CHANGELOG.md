# Changelog

## 0.1.5

- Fix QR Reed-Solomon error correction codeword generation.
- Fix QR format-information module placement and fixed dark module handling.
- Add regression coverage for QR codewords and format-bit placement.

## 0.1.4

- Replace the fake QR-like renderer with a real dependency-free QR encoder.
- Force black-on-white terminal QR rendering when ANSI output is available.
- Reject path traversal segments instead of normalizing them away.
- Preserve custom response headers on directory listings.
- Ignore malformed `If-Modified-Since` headers instead of raising.
- Fix directory redirects when query strings are present.
- Remove generated egg-info and bytecode files from version control.
- Modernize packaging license metadata and run tests in the release workflow.

## 0.1.0

Initial release.

- Threaded static file server rooted at a user-selected directory.
- Dependency-free implementation.
- Byte-range support for `GET` and `HEAD` with `206` and `416` handling.
- `q` / `Q` interactive shutdown support.
- CLI options for bind address, port, directory, CORS, custom headers, directory listing policy, open browser, terminal QR display, cache policy, and verbosity controls.
- Range parser and HTTP behavior tests.
