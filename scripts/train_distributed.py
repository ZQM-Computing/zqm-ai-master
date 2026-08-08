"""
Phase 3 multi-node training orchestrator.

Orchestrates LoRA fine-tuning across ZQM-MESH nodes via SSH.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any

MESH_NODES = [
    {"id": "n1", "ip": "192.168.1.224", "port": 8808},
    {"id": "n3", "ip": "192.168.1.78", "port": 8808},
    {"id": "n4", "ip": "192.168.1.228", "port": 8808},
]


def _request(url: str, payload: dict[str, Any] | None = None, timeout: int = 10) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return {"_http_status": exc.code, "_http_reason": exc.reason}
    except Exception as exc:
        return {"_error": str(exc)}


def discover_live_nodes() -> list[dict[str, Any]]:
    live = []
    for node in MESH_NODES:
        resp = _request(f"http://{node['ip']}:{node['port']}/healthz", timeout=5)
        if resp.get("status") == "ok" or (not resp.get("_http_status") and not resp.get("_error")) or "_http_status" not in resp and "_error" not in resp:
            live.append(node)
    return live


def split_dataset(dataset_path: str, num_splits: int) -> list[str]:
    """Split JSONL dataset into N parts for distributed training."""
    import random
    lines = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)
    random.shuffle(lines)
    splits = [[] for _ in range(num_splits)]
    for i, line in enumerate(lines):
        splits[i % num_splits].append(line)
    out_paths = []
    for idx, split in enumerate(splits):
        path = f"{dataset_path}.shard-{idx}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for line in split:
                f.write(line + "\n")
        out_paths.append(path)
    return out_paths


def submit_training_job(node: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Submit a training job to a mesh node."""
    url = f"http://{node['ip']}:{node['port']}/api/train/lora"
    return _request(url, payload=job, timeout=10)


def orchestrate(
    base_model: str,
    dataset_path: str,
    output_dir: str,
    epochs: int = 1,
    lora_rank: int = 4,
) -> dict[str, Any]:
    """Orchestrate training across live mesh nodes."""
    live = discover_live_nodes()
    print(f"Live nodes: {[n['id'] for n in live]}")
    if not live:
        return {"error": "no live nodes"}

    shards = split_dataset(dataset_path, len(live))
    jobs = []
    for node, shard in zip(live, shards):
        job = {
            "base_model": base_model,
            "dataset_path": shard,
            "output_dir": f"{output_dir}/{node['id']}",
            "epochs": epochs,
            "lora_rank": lora_rank,
        }
        resp = submit_training_job(node, job)
        jobs.append({"node": node["id"], "shard": shard, "resp": resp})
    return {"jobs": jobs, "nodes": len(live)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 multi-node training orchestrator")
    parser.add_argument("--base-model", default="distilgpt2")
    parser.add_argument("--dataset", default="data/training_data_all.jsonl")
    parser.add_argument("--output-dir", default="models/distributed")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--lora-rank", type=int, default=4)
    args = parser.parse_args()
    result = orchestrate(args.base_model, args.dataset, args.output_dir, args.epochs, args.lora_rank)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
