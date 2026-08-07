# ZQM-AI-Master AGI Research System
**Project:** General Intelligence System  
**Target:** Frontier-class capabilities via local-first architecture  
**Current Phase:** Phase 1 — Foundation  
**Version:** 0.1.0-alpha  
**Date:** 2026-08-07

---

## Table of Contents

1. [Mission & Scope](#1-mission--scope)
2. [System Architecture](#2-system-architecture)
3. [Current State (August 2026)](#3-current-state-august-2026)
4. [Compute Infrastructure](#4-compute-infrastructure)
5. [Training Pipeline](#5-training-pipeline)
6. [Reasoning Framework](#6-reasoning-framework)
7. [Evaluation & Benchmarking](#7-evaluation--benchmarking)
8. [Safety & Alignment](#8-safety--alignment)
9. [Development Roadmap](#9-development-roadmap)
10. [Contributing & Extension](#10-contributing--extension)
11. [Glossary](#11-glossary)

---

## 1. Mission & Scope

### 1.1 Objective
Build a general intelligence system that rivals frontier models (GPT-5-class) through:
- Local-first architecture (no cloud API dependencies)
- Open research in training, reasoning, and alignment
- Distributed compute across owned hardware
- Transparent, auditable, reproducible methodology

### 1.2 Scope Boundaries
**IN SCOPE:**
- Fine-tuning and continued pretraining of open-weights models
- Novel reasoning architectures (chain-of-thought, tree-of-thought, multi-agent)
- Safety research: interpretability, robustness, alignment techniques
- Distributed training infrastructure
- Open-source tooling and datasets

**OUT OF SCOPE:**
- Scaled pretraining from scratch (requires $100M+ compute)
- Competing with closed models on pure benchmark scores alone
- Production deployment at frontier scale
- Proprietary data licensing

### 1.3 Success Metrics
| Tier | Metric | Target | Current |
|------|--------|--------|---------|
| Reasoning | MMLU (5-shot) | ≥ 85% | ~45% (qwen2.5:3b) |
| Reasoning | GSM8K | ≥ 80% | ~55% (qwen2.5:3b) |
| Code | HumanEval | ≥ 70% | ~35% (qwen2.5:3b) |
| Safety | TruthfulQA | ≥ 75% | ~50% |
| Efficiency | Tokens/sec (local) | ≥ 50 | ~20 (qwen2.5:3b) |

---

## 2. System Architecture

### 2.1 High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     ZQM-AI-Master AGI Stack                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Training    │    │  Inference   │    │  Evaluation      │  │
│  │  Pipeline    │◄──►│  Engine      │◄──►│  Harness         │  │
│  │  (LoRA/QLoRA)│    │  (Ollama)    │    │  (Benchmarks)    │  │
│  └──────┬───────┘    └──────┬───────┘    └────────┬─────────┘  │
│         │                    │                     │            │
│         ▼                    ▼                     ▼            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Model Registry & Checkpoint Store             │  │
│  │         (Local FS + Versioned Checkpoints)                 │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │              Memory & Knowledge Layer                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐   │  │
│  │  │ Flatspace  │  │ Meilisearch│  │   SearXNG Web      │   │  │
│  │  │ (SQLite)   │  │ (FT Index) │  │   Augmentation     │   │  │
│  │  └────────────┘  └────────────┘  └────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │              Reasoning & Agent Layer                       │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐   │  │
│  │  │ Chain-of-  │  │ Multi-Agent│  │  Self-Improvement  │   │  │
│  │  │ Thought    │  │  Council   │  │  Loop              │   │  │
│  │  └────────────┘  └────────────┘  └────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │              Safety & Alignment Layer                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐   │  │
│  │  │Constitutional│ │Red-Teaming│  │  Interpretability  │   │  │
│  │  │ AI (CAI)   │  │ Framework  │  │  Tools             │   │  │
│  │  └────────────┘  └────────────┘  └────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │              Infrastructure Layer                          │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐   │  │
│  │  │ ZQM-MESH   │  │ NSSM       │  │  Docker Stack      │   │  │
│  │  │ (4 nodes)  │  │ Services   │  │  (Meilisearch,     │   │  │
│  │  │            │  │ (Windows)  │  │   SearXNG, etc.)   │   │  │
│  │  └────────────┘  └────────────┘  └────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Map

| Layer | Component | Purpose | Status |
|-------|-----------|---------|--------|
| Training | LoRA/QLoRA fine-tuning | Adapt models to domain/data | 🔄 Planned |
| Training | Dataset builder | Convert Flatspace → training data | 🔄 Planned |
| Training | Checkpoint manager | Versioned model snapshots | 🔄 Planned |
| Inference | Ollama runtime | Local model serving | ✅ Live |
| Inference | Mesh router | Distribute inference across nodes | 🔄 Partial |
| Memory | Flatspace (SQLite) | Durable chunk store | ✅ Live (918 chunks) |
| Memory | Meilisearch | Full-text search index | ✅ Live (918 docs) |
| Memory | SearXNG | Web augmentation | ✅ Live |
| Reasoning | Chain-of-thought | Step-by-step reasoning | 🔄 Planned |
| Reasoning | Tree-of-thought | Explore reasoning paths | 🔄 Planned |
| Reasoning | Multi-agent council | Specialist agents | ✅ Partial |
| Reasoning | Self-reflection | Critique and improve | 🔄 Planned |
| Safety | Constitutional AI | Rule-based guardrails | 🔄 Planned |
| Safety | Red-teaming | Adversarial testing | 🔄 Planned |
| Safety | Interpretability | Attention/probing analysis | 🔄 Planned |
| Infra | ZQM-MESH | 4-node Windows cluster | ✅ Live |
| Infra | NSSM services | Windows service supervision | ✅ Live |
| Infra | Docker stack | Meilisearch, SearXNG, etc. | ✅ Live |

### 2.3 Data Flow

**Training Flow:**
```
Flatspace DB → Dataset Builder → Train/Val Split → LoRA Fine-tune 
    → Checkpoint → Evaluation → Merge → Deploy to Ollama
```

**Inference Flow:**
```
Query → Flatspace Search (local semantic) → Meilisearch Fallback 
    → SearXNG Augmentation (optional) → Context Assembly 
    → LLM Generation → Response
```

**Self-Improvement Flow:**
```
Task Execution → Outcome Evaluation → Generate Training Data 
    → Fine-tune → A/B Test → Merge if improved
```

---

## 3. Current State (August 2026)

### 3.1 What Works
- **RAG Pipeline**: Local semantic search via Ollama `all-minilm:latest` embeddings
- **Memory Store**: 918 chunks in SQLite (734 filesystem, 184 bitgarden/pollenstore/waxcell)
- **Search Index**: 918 docs synced to Meilisearch with full-text fallback
- **Web Augmentation**: SearXNG integration for live context
- **Service Layer**: FastAPI on port 8808, supervised by NSSM
- **Multi-Agent**: Council patterns, task routing, JWT auth
- **Mesh**: 4-node Windows cluster with Docker services

### 3.2 What’s Missing
- **Training pipeline**: No LoRA/QLoRA fine-tuning yet
- **Evaluation**: No standardized benchmark suite
- **Reasoning**: No CoT/ToT beyond basic prompt engineering
- **Safety**: No constitutional AI, red-teaming, or interpretability
- **Scaling**: Single-node inference, no distributed training
- **Self-improvement**: No automated feedback loops

### 3.3 Codebase Health
- **Language**: Python 3.12, FastAPI, SQLite, Ollama
- **Structure**: Modular routers/services/models
- **Testing**: Manual verification only
- **Docs**: This document + inline code comments

---

## 4. Compute Infrastructure

### 4.1 Current Hardware

| Node | Hostname | IP | Role | GPU | RAM | Status |
|------|----------|-----|------|-----|-----|--------|
| N4 | ZQM-Void-N4 | 192.168.1.228 | Primary/Queen | TBD | TBD | ✅ Active |
| N1 | ZQM-Void-N1 | 192.168.1.224 | Backup/Queen | TBD | TBD | ✅ Active |
| N3 | ZQM-Node-3 | 192.168.1.78 | Worker | TBD | TBD | ✅ Active |
| N2 | ZQM-Node-2 | 192.168.1.31 | Worker | TBD | TBD | ⚠️ Powered off |

**Action Required:** Run `app/main.py` or `diagnostics-engines` skill to inventory actual GPU/RAM specs.

### 4.2 Software Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12 | Runtime |
| FastAPI | Latest | API framework |
| Ollama | Latest | Model serving |
| Meilisearch | v1.11.3 | Search index |
| SearXNG | Latest | Web search |
| Docker | Latest | Service orchestration |
| NSSM | Latest | Windows service supervision |

### 4.3 Scaling Path

**Phase 1 (Now): Single-node fine-tuning**
- LoRA/QLoRA on 7B-13B models
- Single GPU, 16-24GB VRAM
- Expected throughput: 1-2 it/s on 7B, 0.5-1 it/s on 13B

**Phase 2 (Weeks): Multi-node inference**
- Distribute inference across N1/N3/N4
- Model sharding for 13B-30B models
- Expected throughput: 3-5 it/s aggregate

**Phase 3 (Months): Distributed training**
- DeepSpeed/FSDP across 2-4 nodes
- 30B-70B model fine-tuning
- Expected throughput: 0.1-0.5 it/s aggregate

**Phase 4 (Future): Cluster expansion**
- Add dedicated GPU nodes (RTX 4090/A100)
- NVLink/InfiniBand interconnect
- Target: 70B-405B model training

---

## 5. Training Pipeline

### 5.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Training Pipeline v1.0                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │ Data Source  │───► │ Dataset      │───► │ Training Loop    │  │
│  │              │    │ Builder      │    │ (LoRA/QLoRA)     │  │
│  │ - Flatspace  │    │              │    │                  │  │
│  │ - Web aug    │    │ - Extract    │    │ - Optimizer      │  │
│  │ - Synthetic  │    │ - Chunk      │    │ - Scheduler      │  │
│  │ - User      │    │ - Tokenize   │    │ - Grad accum     │  │
│  └──────────────┘    └──────────────┘    └────────┬─────────┘  │
│                                                   │             │
│  ┌──────────────┐    ┌──────────────┐    ┌────────▼─────────┐  │
│  │ Evaluation   │◄──► │ Checkpoint   │◄──► │ Model Registry   │  │
│  │ Harness      │    │ Manager      │    │                  │  │
│  │              │    │              │    │ - Versioning     │  │
│  │ - Benchmarks │    │ - Save/load  │    │ - Rollback       │  │
│  │ - Metrics    │    │ - Cleanup    │    │ - A/B testing    │  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Dataset Builder

**Purpose:** Convert Flatspace chunks + web augmentation into training data.

**Input:**
- Flatspace SQLite: `app/flatspace_local.db`
- SearXNG results: `/api/rag/query?web_augment=true`
- Synthetic data: LLM-generated Q/A pairs

**Output:**
- JSONL files: `training_data.jsonl`
- Format: `{"prompt": "...", "completion": "...", "metadata": {...}}`

**Implementation:** `scripts/build_training_dataset.py` (planned)

### 5.3 Fine-tuning Strategy

**Phase 1: LoRA (Low-Rank Adaptation)**
- Target models: `qwen2.5:7b`, `llama3:8b`, `mistral:7b`
- Rank: 8-16, Alpha: 16-32
- Target modules: q_proj, v_proj, k_proj, o_proj
- Learning rate: 2e-4 to 5e-4
- Batch size: 4-8 (gradient accumulation 16-32)
- Expected VRAM: 12-16GB

**Phase 2: QLoRA (Quantized LoRA)**
- 4-bit quantization + LoRA
- Target models: `llama3:13b`, `qwen2.5:14b`
- Expected VRAM: 8-12GB

**Phase 3: Full Fine-tuning**
- DeepSpeed ZeRO-3
- Target models: 30B-70B
- Expected VRAM: 80GB+ (A100)

### 5.4 Training Loop

```python
# Pseudocode
for epoch in range(epochs):
    for batch in dataset:
        loss = model(batch)
        loss.backward()
        optimizer.step()
        scheduler.step()
        
        if step % eval_interval == 0:
            metrics = evaluate(model, val_set)
            if metrics['score'] > best_score:
                save_checkpoint(model, metrics)
                best_score = metrics['score']
```

### 5.5 Checkpoint Management

**Format:**
```
models/
├── base/
│   ├── qwen2.5-7b/
│   └── llama3-8b/
├── lora/
│   ├── qwen2.5-7b-zqm-v1/
│   │   ├── adapter_config.json
│   │   ├── adapter_model.safetensors
│   │   └── training_args.json
│   └── llama3-8b-zqm-v1/
└── merged/
    ├── qwen2.5-7b-zqm-merged-v1/
    └── llama3-8b-zqm-merged-v1/
```

**Versioning:** Semantic versioning (MAJOR.MINOR.PATCH)
- MAJOR: Architecture change
- MINOR: New dataset/training run
- PATCH: Bug fix, small adjustment

---

## 6. Reasoning Framework

### 6.1 Reasoning Patterns

**Chain-of-Thought (CoT)**
```python
prompt = """Question: {question}
Let's think step by step:
Step 1: ...
Step 2: ...
...
Answer:"""
```

**Tree-of-Thought (ToT)**
```python
# Generate multiple reasoning paths
paths = [generate_path(question) for _ in range(5)]
# Evaluate each path
scores = [evaluate_path(p) for p in paths]
# Select best
best_path = max(paths, key=scores)
```

**Self-Consistency**
```python
# Generate multiple completions
completions = [generate(question) for _ in range(5)]
# Vote on answers
answers = [extract_answer(c) for c in completions]
final = majority_vote(answers)
```

**Constitutional AI (CAI)**
```python
prompt = """Question: {question}
Draft answer: {draft}
Critique against principles:
1. Helpful
2. Harmless
3. Honest
Revised answer:"""
```

### 6.2 Multi-Agent Architecture

**Council Pattern:**
```python
council = Council(
    agents=[
        ReasoningAgent("ZQM-Reasoning-001"),
        CodeAgent("ZQM-Code-Gen"),
        SecurityAgent("ZQM-Security-Sentinel"),
        DataAgent("ZQM-FLATSPACE-Lattice"),
        InfraAgent("ZQM-Infra-Monitor"),
    ],
    chair=ReasoningAgent("ZQM-Reasoning-001"),
    synthesis=MemoryAgent("ZQM-Memory-Store")
)

result = council.deliberate(question)
```

**Specialist Selection:**
```python
def select_agents(question: str) -> List[Agent]:
    # Classify question domain
    domain = classify(question)
    # Select relevant specialists
    return AGENT_REGISTRY[domain]
```

### 6.3 Memory-Augmented Reasoning

**Pattern:**
```python
# Retrieve relevant memories
memories = flatspace.search(question, tier='bitgarden', limit=5)
# Augment prompt
prompt = f"""Context from memory:
{format_memories(memories)}

Question: {question}

Reasoning:"""
```

**Implementation:** Already in `/api/rag/query`

### 6.4 Tool Use & Planning

**ReAct Pattern:**
```python
prompt = """Question: {question}
Thought: I need to ...
Action: tool_name
Action Input: {{"param": "value"}}
Observation: {tool_result}
... (repeat)
Final Answer:"""
```

**Implementation:** Planned for `app/routers/agent.py`

---

## 7. Evaluation & Benchmarking

### 7.1 Benchmark Suite

| Benchmark | Domain | Format | Target | Current |
|-----------|--------|--------|--------|---------|
| MMLU | Knowledge | 5-shot MCQ | ≥ 85% | ~45% |
| GSM8K | Math | 8-shot CoT | ≥ 80% | ~55% |
| HumanEval | Code | 0-shot | ≥ 70% | ~35% |
| TruthfulQA | Safety | 0-shot | ≥ 75% | ~50% |
| MT-Bench | Conversation | Chat | ≥ 8.0 | ~5.5 |
| HELM | Comprehensive | Multi | ≥ 80% | ~40% |

### 7.2 Evaluation Harness

**Script:** `scripts/eval_benchmark.py` (planned)

**Features:**
- Automated benchmark running
- Metrics: accuracy, latency, tokens/sec
- Comparison across model versions
- Regression detection

**Example Usage:**
```bash
python scripts/eval_benchmark.py \
  --model qwen2.5-7b-zqm-v1 \
  --benchmarks mmlu gsm8k humaneval \
  --output results.json
```

### 7.3 Custom Evaluations

**Domain-Specific:**
- ZQM-MESH operations: mesh coordination, service management
- Code generation: Python, PowerShell, Docker
- Security: vulnerability detection, audit patterns

**Safety Evaluations:**
- Jailbreak resistance
- Harmful content detection
- Truthfulness/honesty
- Bias/fairness

---

## 8. Safety & Alignment

### 8.1 Principles

1. **Transparency**: All training data, models, and evaluations are auditable
2. **Beneficence**: Systems should help, not harm
3. **Autonomy**: Users control their data and models
4. **Justice**: Fairness, non-discrimination, accessibility
5. **Accountability**: Clear responsibility for system behavior

### 8.2 Safety Layers

**Layer 1: Constitutional AI (CAI)**
```python
PRINCIPLES = [
    "Never provide instructions for illegal activities",
    "Never generate harmful or dangerous content",
    "Always acknowledge uncertainty",
    "Cite sources when possible",
    "Avoid hallucination; say 'I don't know' when unsure"
]
```

**Layer 2: Red-Teaming**
```python
red_team = RedTeamFramework(
    attack_types=[
        "jailbreak",
        "prompt_injection",
        "data_extraction",
        "bias_exploitation",
        "hallucination_induction"
    ]
)
vulnerabilities = red_team.test(model)
```

**Layer 3: Interpretability**
- Attention visualization
- Activation patching
- Probing classifiers
- Feature attribution

**Layer 4: Robustness**
- Adversarial training
- Input validation
- Output filtering
- Confidence calibration

### 8.3 Alignment Techniques

**RLVR (Reinforcement Learning from Verified Responses)**
```python
# Verified responses from human/expert
verified_data = load_verified_responses()
# Train model to prefer verified responses
model = rlvr_train(model, verified_data)
```

**DPO (Direct Preference Optimization)**
```python
# Preferred vs rejected pairs
preferences = load_preferences()
model = dpo_train(model, preferences)
```

**Self-Critique**
```python
draft = generate(question)
critique = generate(f"Critique this answer: {draft}")
final = generate(f"Improve based on critique: {critique}")
```

---

## 9. Development Roadmap

### Phase 1: Foundation (Now — 4 weeks)
**Goal:** Build working training + eval pipeline

- [x] RAG system operational
- [x] Meilisearch sync
- [x] SearXNG augmentation
- [ ] LoRA fine-tuning script
- [ ] Dataset builder from Flatspace
- [ ] Evaluation harness (MMLU, GSM8K)
- [ ] Checkpoint manager
- [ ] Model registry UI

**Deliverable:** Fine-tuned 7B model on local corpus, eval suite showing +5-10% on domain tasks

### Phase 2: Reasoning (Weeks 5-8)
**Goal:** Implement advanced reasoning patterns

- [ ] Chain-of-thought prompt templates
- [ ] Tree-of-thought explorer
- [ ] Self-consistency voting
- [ ] Constitutional AI guardrails
- [ ] ReAct tool use pattern
- [ ] Multi-agent council v2

**Deliverable:** Model with measurable reasoning improvement on logic/math benchmarks

### Phase 3: Scaling (Weeks 9-16)
**Goal:** Distributed training + larger models

- [ ] DeepSpeed ZeRO-3 integration
- [ ] Multi-node training orchestration
- [ ] 13B model fine-tuning
- [ ] Model parallelism for 30B+
- [ ] Inference optimization (quantization, caching)

**Deliverable:** 13B model trained across 2+ nodes, 2x inference throughput

### Phase 4: Safety (Ongoing)
**Goal:** Robust safety + alignment

- [ ] Red-teaming framework
- [ ] Interpretability tools
- [ ] DPO/RLVR alignment
- [ ] Benchmarking on safety datasets
- [ ] Adversarial robustness testing

**Deliverable:** Safety report, vulnerability assessment, mitigation strategies

### Phase 5: Self-Improvement (Months 5+)
**Goal:** Closed-loop learning system

- [ ] Automated feedback collection
- [ ] Training data generation from interactions
- [ ] A/B testing framework
- [ ] Automatic fine-tuning triggers
- [ ] Performance regression detection

**Deliverable:** System that improves without human intervention (within safety bounds)

---

## 10. Contributing & Extension

### 10.1 Adding a New Reasoning Pattern

```python
# app/reasoning/patterns/my_pattern.py
from app.reasoning.base import ReasoningPattern

class MyPattern(ReasoningPattern):
    name = "my_pattern"
    
    async def apply(self, question: str, context: str) -> str:
        # Your reasoning logic
        prompt = self.build_prompt(question, context)
        response = await self.llm.generate(prompt)
        return self.post_process(response)
```

**Register:**
```python
# app/reasoning/__init__.py
from app.reasoning.patterns.my_pattern import MyPattern
PATTERNS.register(MyPattern())
```

### 10.2 Adding a New Benchmark

```python
# app/evaluation/benchmarks/my_benchmark.py
from app.evaluation.base import Benchmark

class MyBenchmark(Benchmark):
    name = "my_benchmark"
    description = "Custom benchmark"
    
    async def run(self, model) -> Dict[str, Any]:
        # Load dataset
        # Run model on each item
        # Calculate metrics
        return {"accuracy": ..., "latency": ...}
```

### 10.3 Adding a New Safety Check

```python
# app/safety/checks/my_check.py
from app.safety.base import SafetyCheck

class MyCheck(SafetyCheck):
    name = "my_check"
    
    async def evaluate(self, response: str) -> SafetyResult:
        # Your safety logic
        return SafetyResult(passed=..., severity=..., message=...)
```

---

## 11. Glossary

| Term | Definition |
|------|-----------|
| **AGI** | Artificial General Intelligence — a system that can perform any intellectual task a human can |
| **RAG** | Retrieval-Augmented Generation — combining retrieval with LLM generation |
| **LoRA** | Low-Rank Adaptation — parameter-efficient fine-tuning |
| **QLoRA** | Quantized LoRA — 4-bit quantized LoRA for lower VRAM |
| **CoT** | Chain-of-Thought — step-by-step reasoning |
| **ToT** | Tree-of-Thought — exploring multiple reasoning paths |
| **CAI** | Constitutional AI — rule-based alignment |
| **DPO** | Direct Preference Optimization — alignment from preferences |
| **RLVR** | Reinforcement Learning from Verified Responses |
| **Flatspace** | Local SQLite-based knowledge store |
| **Meilisearch** | Full-text search engine for document indexing |
| **SearXNG** | Self-hosted web search meta-engine |
| **ZQM-MESH** | 4-node Windows cluster for distributed compute |
| **NSSM** | Non-Sucking Service Manager — Windows service supervisor |
| **Ollama** | Local LLM inference engine |
| **DeepSpeed** | Microsoft's distributed training framework |
| **ZeRO** | Zero Redundancy Optimizer — memory-efficient distributed training |

---

## Appendix A: Quick Reference

### Start the system
```powershell
nssm start ZQM-Void-N4
```

### Stop the system
```powershell
nssm stop ZQM-Void-N4
```

### Query RAG
```bash
TOKEN=$(python -c "from app.core.security import create_access_token; print(create_access_token('zqmco-admin'))")
curl -X POST http://127.0.0.1:8808/api/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"your question","tier":"filesystem","limit":5}'
```

### Ingest data
```bash
python scripts/ingest_c_drive.py --roots C:/Void C:/Users/zqmco --max-depth 5
```

### Sync Meilisearch
```bash
python scripts/sync_meili.py
```

### Check service status
```powershell
nssm status ZQM-Void-N4
netstat -ano | grep LISTENING | grep ":8808"
```

---

## Appendix B: Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI entry point |
| `app/routers/rag.py` | RAG query endpoint |
| `app/services/flatspace_service.py` | Memory layer orchestration |
| `app/services/meilisearch_service.py` | Meilisearch integration |
| `app/core/config.py` | Configuration/settings |
| `app/core/security.py` | JWT auth |
| `scripts/ingest_c_drive.py` | Filesystem ingestion |
| `scripts/sync_meili.py` | Meilisearch sync |
| `scripts/rag_bootstrap.py` | RAG initialization |
| `app/flatspace_local.db` | SQLite knowledge store |
| `.env` | Environment variables |

---

## Appendix C: Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | JWT signing key | `changeme-please-generate-with-openssl-rand-hex-32` |
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://127.0.0.1:11434` |
| `OLLAMA_DEFAULT_MODEL` | Default model | `qwen2.5:3b` |
| `MEILISEARCH_URL` | Meilisearch endpoint | `http://127.0.0.1:7701` |
| `MEILISEARCH_MASTER_KEY` | Meilisearch auth | (empty) |
| `SEARXNG_URL` | SearXNG endpoint | `http://127.0.0.1:8080` |
| `FLATSPACE_MODE` | `local` or `auto` | `auto` |
| `ENVIRONMENT` | `development`/`production` | `development` |

---

**This document is the canonical reference for the ZQM-AI-Master AGI research system. All development should align with the architecture and roadmap defined here.**

**Next Review:** 2026-08-14
