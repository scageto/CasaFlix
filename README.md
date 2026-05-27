# CasaFlix

Static front-end that browses the [vixsrc.to](https://vixsrc.to) catalog with
metadata enriched via [TMDB](https://www.themoviedb.org/), and plays titles
through either **Vix** or **VidSrc** as the streaming provider.

The catalog is pre-built into `data/movies.json` + `data/tv.json` so visitors do
**not** need their own TMDB key.

The repo is designed to be hosted on GitHub Pages.

## Features

- **Two streaming providers**: pick Vix or VidSrc from the header toggle.
  Choice is remembered per browser.
- **In-page iframe player** with automatic fallback: if the primary provider
  doesn't respond within 8 seconds, the secondary is tried automatically.
  Manual "↻ Cambia provider" and "↗ Apri in nuova scheda" buttons are always
  available.
- **Filters & sorting**: filter the grid by genre and year, sort by year
  (asc/desc) or vote (asc/desc).
- **Search** by title (combines with active filters).
- **Lazy loading**: only the active tab's catalog (Film or Serie TV) is fetched
  on first paint; the other loads on first click.

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

This writes two minified files: `data/movies.json` and `data/tv.json`, sorted
by year descending (newest first). Together they replace the legacy
`data/catalog.json`.

Useful flags:

| Flag                          | Purpose                                                          |
| ----------------------------- | ---------------------------------------------------------------- |
| `--limit 5`                   | dry-run, process only first 5 ids per type                       |
| `--no-cache`                  | force a full re-fetch (ignore + don't update cache)              |
| `--workers 10`                | concurrent TMDB fetch workers (default 10)                       |
| `--sleep 0`                   | per-call politeness sleep in seconds (default 0)                 |
| `--out-dir data`              | output directory for `movies.json` + `tv.json` (default `data`)  |
| `--cache data/.cache.json`    | cache path (default `data/.cache.json`)                          |

The script polls the vix list endpoints (`/api/list/movie`, `/api/list/tv`),
deduplicates the TMDB ids, and fetches each one from TMDB in parallel.
Responses are cached in `data/.cache.json` (gitignored), so subsequent runs
only hit TMDB for new ids.

A full cold-cache build of ~17k titles takes **~10–15 minutes** with 10
workers. Subsequent warm-cache runs complete in under a minute.

## Previewing locally

```bash
python -m http.server 8000
# open http://localhost:8000
```

`fetch('data/movies.json')` does not work over `file://`, so a local server
is required.

## Deploying to GitHub Pages

1. Push the repo to GitHub.
2. **Settings → Pages → Build and deployment → Deploy from a branch**, pick
   `main` / root.

## Automating catalog refresh

The included GitHub Actions workflow (`.github/workflows/update-catalog.yml`)
regenerates `data/movies.json` + `data/tv.json` weekly (Mondays 04:00 UTC)
and on manual dispatch.

To enable it on your fork:

1. **Settings → Secrets and variables → Actions → New repository secret**:
   add `TMDB_API_KEY` with your v4 token.
2. **Actions** tab → enable workflows if prompted.
3. **Settings → Actions → General → Workflow permissions** must be
   "Read and write permissions" (default on new repos).
4. The workflow commits any changes back to the default branch with the
   `github-actions[bot]` identity. If the catalog is byte-identical it
   skips the commit.

## Tests

```bash
pytest -v
```

## Notes on the player and providers

- The provider URL patterns used by the front-end:
  - Vix:    `https://vixsrc.to/movie/{tmdb}?lang=it` ·
            `https://vixsrc.to/tv/{tmdb}/{season}/{episode}?lang=it`
  - VidSrc: `https://vidsrc-embed.ru/embed/movie?tmdb={tmdb}&ds_lang=it` ·
            `https://vidsrc-embed.ru/embed/tv?tmdb={tmdb}&season={s}&episode={e}&ds_lang=it`
- The catalog list itself comes from **vix only** (its `/api/list/{movie,tv}`
  endpoints); VidSrc is purely an alternate playback target for the same
  TMDB ids. Titles vix doesn't have are not browsable, regardless of provider.
- Cross-origin restrictions prevent the page from detecting whether the
  embedded player actually plays the video. Automatic fallback only catches
  the hard-failure case (no `iframe.onload` within 8 s). For a player that
  loads an "unavailable" page inside, use the manual "Cambia provider" button.

## Credits

Streaming providers: [vixsrc.to](https://vixsrc.to), [vidsrc-embed.ru](https://vidsrc-embed.ru).
Metadata: [TMDB](https://www.themoviedb.org/).
This product uses the TMDB API but is not endorsed or certified by TMDB.
