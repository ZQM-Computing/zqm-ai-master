import json
import statistics
import time
import urllib.request

BACKENDS = [
    ("N4", "http://192.168.1.228:11434"),
    ("N3", "http://192.168.1.78:11434"),
    ("N1", "http://192.168.1.224:11434"),
    ("N2", "http://192.168.1.31:11434"),
]
MODELS = [
    "qwen2.5:0.5b",
    "qwen2.5:3b",
    "llama3.2:3b",
    "gemma4:latest",
    "llava:7b",
    "phi3:mini",
]
PROMPT = "Write exactly 200 words about distributed AI inference across mesh nodes."
TARGET_TOKENS = 200
N_RUNS = 3

def tags(base):
    req = urllib.request.Request(base + "/api/tags", method="GET")
    with urllib.request.urlopen(req, timeout=15) as r:
        return {m["name"] for m in json.loads(r.read()).get("models", [])}

def generate(base, model, prompt, timeout=25):
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"num_predict": TARGET_TOKENS, "temperature": 0.0},
    }).encode()
    req = urllib.request.Request(base + "/api/generate", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    first = None
    total_tokens = 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except Exception:
                continue
            if first is None and chunk.get("response"):
                first = time.time()
            if chunk.get("done"):
                total_tokens = chunk.get("eval_count", total_tokens)
                break
    t1 = time.time()
    ttft = (first - t0) if first else None
    total = t1 - t0
    tps = total_tokens / total if total > 0 and total_tokens else None
    return {"ttft_s": ttft, "total_s": total, "tokens": total_tokens, "tps": tps}

def main():
    results = []
    for name, base in BACKENDS:
        available = tags(base)
        print(f"\n=== {name} ({base}) — {len(available)} models ===")
        for model in MODELS:
            if model not in available:
                continue
            runs = []
            for i in range(N_RUNS):
                try:
                    runs.append(generate(base, model, PROMPT))
                except Exception as e:
                    runs.append({"error": str(e)[:80]})
            ok = [r for r in runs if "error" not in r]
            if not ok:
                print(f"  {model:30} ERR {runs[0].get('error','?')}")
                continue
            tps_vals = [r["tps"] for r in ok if r.get("tps")]
            ttft_vals = [r["ttft_s"] for r in ok if r.get("ttft_s") is not None]
            total_vals = [r["total_s"] for r in ok]
            tokens_vals = [r["tokens"] for r in ok]
            avg_tps = statistics.mean(tps_vals) if tps_vals else None
            avg_ttft = statistics.mean(ttft_vals) if ttft_vals else None
            avg_total = statistics.mean(total_vals)
            avg_tokens = statistics.mean(tokens_vals)
            tps_str = f"{avg_tps:.2f}" if avg_tps else "?"
            print(f"  {model:30} tokens={avg_tokens:.0f}  total={avg_total:.2f}s  ttft={avg_ttft:.2f}s  tps={tps_str:>6}  n={len(ok)}")
            results.append({
                "node": name, "model": model, "tokens": avg_tokens,
                "total_s": avg_total, "ttft_s": avg_ttft, "tps": avg_tps, "n": len(ok)
            })
    with open("benchmark_tokens_per_sec.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved benchmark_tokens_per_sec.json")

if __name__ == "__main__":
    main()
