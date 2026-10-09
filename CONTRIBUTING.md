# Contributing to dokhaneh

Thanks for helping! Issues and pull requests in **English or Persian** are welcome.
Good places to start: issues labelled [`good first issue`](https://github.com/mrzroot/dokhaneh/labels/good%20first%20issue).

## Development setup

```bash
git clone https://github.com/mrzroot/dokhaneh && cd dokhaneh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Before you open a pull request

```bash
ruff check src tests
ruff format --check src tests
pytest -v
```

Tests never touch real GitHub, ArvanCloud, Liara or Gitea accounts: use the temp-project and key fixtures in
`tests/conftest.py`, `dry_run=True`, and `monkeypatch` for network calls (see `tests/test_publish.py`).

## Where things live

| Path | What |
|---|---|
| `src/dokhaneh/cli.py` | Typer CLI: `init`, `keygen`, `sign`, `install-script`, `publish`, `verify`, `status` |
| `src/dokhaneh/targets/` | One module per target (`github.py`, `s3.py`, `gitea.py`) on top of `base.py` |
| `src/dokhaneh/manifest.py` | Manifest building and Ed25519 signing |
| `src/dokhaneh/installer.py` | The generated `install.sh` with mirror fallback |
| `src/dokhaneh/verify.py` | Signature and mirror consistency checks |
| `action.yml` | The GitHub Action |

## Adding a target

Subclass `Target` in `targets/base.py` and implement `validate()`, `publish(bundle, dry_run)` and
`check(client)`, plus the URL helpers your host needs. Register it in `REGISTRY` in `targets/__init__.py`,
add tests that do not need an account, and document the config keys in the README (EN + FA).
dokhaneh only publishes to hosts the project owner controls; it is not a circumvention tool.

## Security

Please report vulnerabilities privately via [GitHub security advisories](https://github.com/mrzroot/dokhaneh/security/advisories/new).
