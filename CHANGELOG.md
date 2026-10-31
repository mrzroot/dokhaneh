# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Documentation, website and test-readability changes only; the package and the GitHub Action are unchanged since 0.1.0.

### Added
- Project website (GitHub Pages, `docs/`), README quick start, CONTRIBUTING, SECURITY and issue templates.
- An animated banner at the top of the README.

### Changed
- Every test file now starts with a docstring saying what it covers.

## [0.1.0] - 2026-10-09

First release: one release, two homes.

### Added
- `dokhaneh.yml` targets: GitHub Releases, ArvanCloud and Liara object storage (S3-compatible, generic S3 too) and Gitea/Forgejo (git mirror push + releases).
- Artifacts and the docs site published to every target.
- Ed25519-signed manifest (SHA-256 and size of every file) and `dokhaneh verify [--deep]` across all mirrors.
- Generated POSIX `install.sh`: global source first, domestic fallbacks, signature and hash checked, tampered mirrors skipped.
- `dokhaneh status`: UP / MISSING / DOWN per target with latency.
- Composite GitHub Action (`uses: mrzroot/dokhaneh@v0.1.0`).

[Unreleased]: https://github.com/mrzroot/dokhaneh/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mrzroot/dokhaneh/releases/tag/v0.1.0
