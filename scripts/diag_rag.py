"""Diagnose RAG path with real runtime calls."""
import asyncio
import json
from app.services.mesh_ollama import router as mesh_ollama
from app.core.config import settings
from app.services.flatspace_local import LocalFlatSpaceStore
from app.routers.rag import _build_context


async def main():
    fs = LocalFlatSpaceStore()
    results = fs.search("quantum simulation flatspace", tier="bitgarden", limit=2)
    print("RESULTS", len(results))
    for r in results:
        print("SCORE", r.get("score"), "KEY", r.get("key"))
    context = _build_context(results)
    print("CONTEXT_LEN", len(context))
    print(context[:1500])
    prompt = (
        "Answer using ONLY the context below. "
        "If the context does not contain the answer, say: I don't know.\n\n"
        f"Context:\n{context}\n\n"
        "Question: quantum simulation flatspace\n\n"
        "Answer:"
    )
    data = await mesh_ollama.chat(
        settings.ollama_default_model,
        [{"role": "user", "content": prompt}],
        timeout=120,
    )
    print("MODEL", data.get("model"))
    print("ANSWER", (data.get("message") or {}).get("content", "")[:500])


if __name__ == "__main__":
    asyncio.run(main())
