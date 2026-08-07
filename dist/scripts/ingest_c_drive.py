"""Ingest text files from filesystem roots into Flatspace local DB as searchable chunks."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(r"C:\Void\ZQM-AI-Master")
DB_PATH = ROOT / "app" / "flatspace_local.db"
OLLAMA_EMBED = "http://127.0.0.1:11434/api/embeddings"
MODEL = "all-minilm:latest"
TIER = "filesystem"
CHUNK_SIZE = 2000
OVERLAP = 200
MAX_FILE_BYTES = 200 * 1024
MAX_CHUNKS_DEFAULT = 10000
WORKERS = 8
MAX_DEPTH_DEFAULT = 5

SKIP_EXT = {
    ".exe", ".dll", ".pyd", ".pyc", ".zip", ".tar", ".gz", ".7z", ".bz2",
    ".xz", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".mp3", ".mp4",
    ".wav", ".avi", ".mov", ".iso", ".vhd", ".vhdx", ".msi", ".cab", ".sys",
    ".dat", ".db", ".sqlite", ".sqlite3", ".pcap", ".class", ".jar", ".war",
    ".whl", ".o", ".a", ".lib", ".obj", ".DS_Store", ".swp", ".swo",
}
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", ".idea",
    ".vscode", ".mypy_cache", ".pytest_cache", "dist", "build", "target",
    "bin", "obj", ".next", ".cache", "Cache", "Code Cache",
    "AppData", "LocalCache", "Packages", "Microsoft", "Google",
}


def chunk_text(text: str) -> list[str]:
    out = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        out.append(text[start:end])
        start = end - OVERLAP
    return out


def embed_batch(texts: list[str], workers: int) -> list[list[float] | None]:
    results: list[list[float] | None] = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(embed_one, t): i for i, t in enumerate(texts)}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                results[i] = fut.result()
            except Exception:
                results[i] = None
    return results


def embed_one(text: str) -> list[float]:
    payload = json.dumps({"model": MODEL, "prompt": text[:4000]}).encode()
    req = urllib.request.Request(OLLAMA_EMBED, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    vec = data.get("embedding")
    if not vec:
        raise RuntimeError("empty embedding")
    return vec


def iter_files(roots: list[Path], max_depth: int) -> list[Path]:
    files = []
    for root in roots:
        if not root.exists():
            continue
        root_str = str(root)
        root_depth = root_str.rstrip("/").count("/")
        stack = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            try:
                with os.scandir(current) as it:
                    entries = sorted(it, key=lambda e: (e.is_file(), e.name))
            except (PermissionError, OSError):
                continue
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    name = entry.name
                    if name in SKIP_DIRS:
                        continue
                    if depth + 1 < max_depth:
                        stack.append((Path(entry.path), depth + 1))
                    continue
                fpath = Path(entry.path)
                ext = fpath.suffix.lower()
                if ext in SKIP_EXT:
                    continue
                try:
                    if entry.stat().st_size > MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                files.append(fpath)
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="*", default=None, help="Filesystem roots to ingest")
    parser.add_argument("--max-chunks", type=int, default=MAX_CHUNKS_DEFAULT)
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--max-depth", type=int, default=MAX_DEPTH_DEFAULT)
    args = parser.parse_args()

    roots = args.roots if args.roots else [Path(r"C:/Users/zqmco"), Path(r"C:/Void")]
    roots = [Path(r) for r in roots]

    print("INGEST_ROOTS", [str(r) for r in roots], flush=True)
    print("DB", DB_PATH, flush=True)
    print("MAX_CHUNKS", args.max_chunks, "MAX_DEPTH", args.max_depth, flush=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS flatspace (
            key TEXT PRIMARY KEY,
            tier TEXT NOT NULL,
            value TEXT NOT NULL,
            metadata TEXT,
            created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            embedding TEXT
        )"""
    )
    conn.commit()

    t_scan0 = time.time()
    files = iter_files(roots, args.max_depth)
    t_scan = time.time() - t_scan0
    print("FILES_SCANNED", len(files), "scan_sec", round(t_scan, 1), flush=True)

    chunks_buffer = []
    seen_keys = set()
    inserted = 0
    skipped_existing = 0

    t0 = time.time()

    for fpath in files:
        if inserted + len(chunks_buffer) >= args.max_chunks:
            break
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not text.strip():
            continue
        parts = chunk_text(text)
        rel = os.path.relpath(str(fpath), str(ROOT))
        for i, part in enumerate(parts):
            key = f"fs:{rel}:{i}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            row = conn.execute("SELECT 1 FROM flatspace WHERE key=?", (key,)).fetchone()
            if row:
                skipped_existing += 1
                continue
            chunks_buffer.append((key, rel, i, part))

    print("CHUNKS_QUEUED", len(chunks_buffer), "skipped_existing", skipped_existing, flush=True)

    batch_size = 64
    batch_num = 0
    while chunks_buffer:
        if inserted >= args.max_chunks:
            break
        batch = chunks_buffer[:batch_size]
        chunks_buffer = chunks_buffer[batch_size:]
        texts = [c[3] for c in batch]
        vecs = embed_batch(texts, args.workers)
        rows = []
        for vec, (key, rel, i, part) in zip(vecs, batch):
            if vec is None:
                continue
            val = json.dumps({"path": rel, "chunk": i, "text": part})
            rows.append((key, TIER, val, json.dumps(vec)))
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO flatspace (key, tier, value, embedding) VALUES (?,?,?,?)",
                rows,
            )
            conn.commit()
            inserted += len(rows)
        batch_num += 1
        if batch_num % 10 == 0:
            elapsed = time.time() - t0
            print(f"progress: inserted={inserted} batches={batch_num} elapsed={elapsed:.1f}s", flush=True)

    elapsed = time.time() - t0
    print(f"DONE: inserted={inserted} elapsed={elapsed:.1f}s", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
