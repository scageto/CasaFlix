# CasaFlix

Static front-end that browses the [vixsrc.to](https://vixsrc.to) catalog with
metadata enriched via [TMDB](https://www.themoviedb.org/). The catalog is
pre-built into `data/catalog.json` so visitors do **not** need their own TMDB key.

The repo is designed to be hosted on GitHub Pages.

## Local development

Requires Python 3.9+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements-dev.txt
```

## Regenerating the catalog

You need a TMDB **v4 Read Access Token** (found at
[themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) →
"API Read Access Token").

```bash
# Option 1: pass via flag
python build_catalog.py --key "<TOKEN>"

# Option 2: env var
export TMDB_API_KEY=<TOKEN>      # PowerShell: $env:TMDB_API_KEY = "<TOKEN>"
python build_catalog.py
```

Useful flags:

| Flag                       | Purpose                                            |
| -------------------------- | -------------------------------------------------- |
| `--limit 5`                | dry-run, only first 5 ids per type                 |
| `--no-cache`               | force a full re-fetch                              |
| `--out path/to/file.json`  | output path (default `data/catalog.json`)          |
| `--cache path/to/cache.json` | cache path (default `data/.cache.json`)          |

The script polls the vix list endpoints (`/api/list/movie`, `/api/list/tv`),
deduplicates the TMDB ids, and fetches each one from TMDB. Responses are
cached in `data/.cache.json` (gitignored), so subsequent runs only hit TMDB
for new or evicted ids.

A full cold-cache build can take **30–60 minutes** because the vix catalog
contains thousands of titles. Subsequent runs with a warm cache complete in
seconds.

## Previewing locally

```bash
python -m http.server 8000
# open http://localhost:8000
```

`fetch('data/catalog.json')` does not work over `file://`, so a local server
is required.

## Deploying to GitHub Pages

1. Push the repo to GitHub.
2. **Settings → Pages → Build and deployment → Deploy from a branch**, pick
   `main` / root.

## Automating catalog refresh

The included GitHub Actions workflow (`.github/workflows/update-catalog.yml`)
regenerates `data/catalog.json` weekly (Mondays 04:00 UTC) and on manual
dispatch.

To enable it on your fork:

1. **Settings → Secrets and variables → Actions → New repository secret**:
   add `TMDB_API_KEY` with your v4 token.
2. **Actions** tab → enable workflows if prompted.
3. The workflow will commit any changes back to the default branch with the
   `github-actions[bot]` identity.

## Tests

```bash
pytest -v
```

## Credits

Streaming provider: [vixsrc.to](https://vixsrc.to). Metadata: [TMDB](https://www.themoviedb.org/).
This product uses the TMDB API but is not endorsed or certified by TMDB.
