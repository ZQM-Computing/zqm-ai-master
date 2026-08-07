"""Independent repro of local semantic search path."""
import json
import sqlite3
import urllib.request
import math

DB_PATH = r"C:\Void\ZQM-AI-Master\app\flatspace_local.db"
OLLAMA_EMBED = "http://127.0.0.1:11434/api/embeddings"
MODEL = "all-minilm:latest"
QUERY = "quantum simulation flatspace"


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)


def embed(text: str):
    payload = json.dumps({"model": MODEL, "prompt": text[:8000]}).encode()
    req = urllib.request.Request(OLLAMA_EMBED, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    vec = data.get("embedding")
    if not vec:
        raise RuntimeError("empty embedding")
    return vec


def main():
    print("DB_PATH", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT key, value, embedding FROM flatspace WHERE tier='bitgarden'").fetchall()
    print("bitgarden_rows", len(rows))
    qv = embed(QUERY)
    print("query_vec_len", len(qv))
    scored = []
    for row in rows:
        raw = row["embedding"]
        if not raw:
            continue
        try:
            vec = json.loads(raw)
        except Exception:
            continue
        sim = cosine(qv, vec)
        scored.append((sim, row["key"], vec))
    scored.sort(key=lambda x: x[0] or -1, reverse=True)
    print("scored_rows", len(scored))
    print("top5")
    for sim, key, vec in scored[:5]:
        print(round(sim, 4), key)
    print("top10_sims", [round(sim, 4) for sim, _, _ in scored[:10]])


if __name__ == "__main__":
    main()
