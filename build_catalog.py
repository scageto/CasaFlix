"""CasaFlix catalog builder."""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

POSTER_BASE = "https://image.tmdb.org/t/p/w342"
BACKDROP_BASE = "https://image.tmdb.org/t/p/w780"


def _img(base: str, path: str | None) -> str | None:
    if not path:
        return None
    return f"{base}{path}"


def _year(date_str: str | None) -> int | None:
    if not date_str or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None


def _vote(value) -> float | None:
    if value is None or value == 0:
        return None
    return round(float(value), 1)


def _genres(raw_genres) -> list[str]:
    return [g["name"] for g in (raw_genres or []) if g.get("name")]


def normalize_movie(raw: dict, en_fallback: dict | None) -> dict:
    title = raw.get("title") or ""
    overview = raw.get("overview") or ""
    if en_fallback:
        if not title:
            title = en_fallback.get("title") or ""
        if not overview:
            overview = en_fallback.get("overview") or ""
    return {
        "tmdb_id": raw["id"],
        "title": title,
        "year": _year(raw.get("release_date")),
        "overview": overview,
        "poster": _img(POSTER_BASE, raw.get("poster_path")),
        "backdrop": _img(BACKDROP_BASE, raw.get("backdrop_path")),
        "vote": _vote(raw.get("vote_average")),
        "genres": _genres(raw.get("genres")),
        "runtime": raw.get("runtime") if raw.get("runtime") else None,
    }


def normalize_tv(raw: dict, en_fallback: dict | None) -> dict:
    title = raw.get("name") or ""
    overview = raw.get("overview") or ""
    if en_fallback:
        if not title:
            title = en_fallback.get("name") or ""
        if not overview:
            overview = en_fallback.get("overview") or ""
    seasons = [
        {"n": s["season_number"], "episodes": s.get("episode_count", 0)}
        for s in (raw.get("seasons") or [])
        if "season_number" in s
    ]
    return {
        "tmdb_id": raw["id"],
        "title": title,
        "year": _year(raw.get("first_air_date")),
        "overview": overview,
        "poster": _img(POSTER_BASE, raw.get("poster_path")),
        "backdrop": _img(BACKDROP_BASE, raw.get("backdrop_path")),
        "vote": _vote(raw.get("vote_average")),
        "genres": _genres(raw.get("genres")),
        "seasons": seasons,
    }


def load_cache(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(path: Path, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


TMDB_BASE = "https://api.themoviedb.org/3"
VIX_LIST_BASE = "https://vixsrc.to/api/list"


def make_session(tmdb_token: str, pool_size: int = 16) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=pool_size,
        pool_maxsize=pool_size,
    )
    s.mount("https://", adapter)
    s.headers.update({
        "Authorization": f"Bearer {tmdb_token}",
        "Accept": "application/json",
        "User-Agent": "CasaFlix-build/1.0",
    })
    return s


def fetch_vix_ids(session: requests.Session, kind: str) -> list[int]:
    url = f"{VIX_LIST_BASE}/{kind}?lang=it"
    r = session.get(url, timeout=15)
    r.raise_for_status()
    items = r.json()
    seen: set[int] = set()
    out: list[int] = []
    for it in items:
        tid = it.get("tmdb_id")
        if tid is None or tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def fetch_tmdb(session: requests.Session, kind: str, tmdb_id: int, language: str) -> dict | None:
    url = f"{TMDB_BASE}/{kind}/{tmdb_id}"
    r = session.get(url, params={"language": language}, timeout=15)
    if r.status_code == 404:
        return None
    if not r.ok:
        return None
    return r.json()


NORMALIZERS = {"movie": normalize_movie, "tv": normalize_tv}


def process_id(
    session: requests.Session,
    kind: str,
    tmdb_id: int,
    cache: dict,
    use_cache: bool,
    sleep: float = 0.05,
    cache_lock: threading.Lock | None = None,
) -> dict | None:
    key = f"{kind}:{tmdb_id}"
    if use_cache:
        if cache_lock:
            with cache_lock:
                hit = cache.get(key)
        else:
            hit = cache.get(key)
        if hit is not None:
            return NORMALIZERS[kind](hit["data"], en_fallback=None)

    raw = fetch_tmdb(session, kind, tmdb_id, "it-IT")
    if raw is None:
        return None

    en = None
    title_field = "title" if kind == "movie" else "name"
    if not raw.get(title_field) or not raw.get("overview"):
        en = fetch_tmdb(session, kind, tmdb_id, "en-US")

    entry = {"fetched_at": datetime.now(timezone.utc).isoformat(), "data": raw}
    if cache_lock:
        with cache_lock:
            cache[key] = entry
    else:
        cache[key] = entry
    if sleep:
        time.sleep(sleep)
    return NORMALIZERS[kind](raw, en_fallback=en)


def build(args) -> int:
    token = args.key or os.environ.get("TMDB_API_KEY")
    if not token:
        print("error: TMDB API key required (--key or TMDB_API_KEY env var)", file=sys.stderr)
        return 2

    workers = max(1, args.workers)
    session = make_session(token, pool_size=max(16, workers * 2))
    cache_path = Path(args.cache)
    cache = {} if args.no_cache else load_cache(cache_path)
    cache_lock = threading.Lock()

    def worker(kind: str, tid: int) -> tuple[int, dict | None, bool]:
        cached_hit = (not args.no_cache) and (f"{kind}:{tid}" in cache)
        norm = process_id(
            session, kind, tid, cache,
            use_cache=not args.no_cache,
            sleep=args.sleep,
            cache_lock=cache_lock,
        )
        return tid, norm, cached_hit

    result: dict[str, list[dict]] = {}
    for kind in ("movie", "tv"):
        ids = fetch_vix_ids(session, kind)
        if args.limit:
            ids = ids[: args.limit]
        total = len(ids)
        print(f"[vix] {kind} list: {total} ids", flush=True)
        items: list[dict] = []
        ok = skipped = cached = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, (tid, norm, cached_hit) in enumerate(
                pool.map(lambda t: worker(kind, t), ids), 1
            ):
                if norm is None:
                    skipped += 1
                else:
                    items.append(norm)
                    ok += 1
                    if cached_hit:
                        cached += 1
                if i % 100 == 0 or i == total:
                    print(f"[tmdb] {kind} progress: {i}/{total} (ok={ok} skipped={skipped} cached={cached})", flush=True)
        print(f"[tmdb] {kind}: {ok} ok, {skipped} skipped, {cached} from cache", flush=True)
        # Sort newest first; items missing year sink to the bottom.
        items.sort(key=lambda it: it.get("year") or -1, reverse=True)
        result[kind] = items

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **result,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out_path)
    size_kb = out_path.stat().st_size / 1024
    print(f"[out] wrote {out_path} ({size_kb:.1f} KB), generated_at={out['generated_at']}")

    if not args.no_cache:
        save_cache(cache_path, cache)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build CasaFlix catalog.json from vixsrc + TMDB")
    p.add_argument("--key", help="TMDB v4 Bearer token (or env TMDB_API_KEY)")
    p.add_argument("--out", default="data/catalog.json", help="Output JSON path")
    p.add_argument("--cache", default="data/.cache.json", help="Cache file path")
    p.add_argument("--no-cache", action="store_true", help="Ignore + overwrite cache")
    p.add_argument("--limit", type=int, default=0, help="Process only first N ids per type (dry-run)")
    p.add_argument("--workers", type=int, default=10, help="Concurrent TMDB fetch workers (default 10)")
    p.add_argument("--sleep", type=float, default=0.0, help="Per-call sleep in seconds (default 0)")
    args = p.parse_args(argv)
    return build(args)


if __name__ == "__main__":
    raise SystemExit(main())
