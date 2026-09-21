# Document Processing Benchmark

An open-source runner for testing whether document parsers preserve the meaning of legal redlines before the parsed text enters a RAG system.

[View the live leaderboard](https://www.openbenchmarks.dev/document-processing) · [Public dataset](https://huggingface.co/datasets/openbenchmarks/OB-LegalQA) · [Source dataset](https://huggingface.co/datasets/crosbylegal/RedlineBench)

## Current benchmark

The benchmark parses redlined contract PDFs, gives each parser's markdown to the same downstream reader, and scores whether the answer reflects the language the parties kept—not text they deleted. This isolates the ingestion layer where a visually present deletion can become false context for every later retrieval and answer.

| Rank | Parser | Answer accuracy |
|---:|---|---:|
| 1 | Claude Fable 5.1 | 89.1% |
| 2 | LlamaParse agentic plus | 80.4% |
| 3 | Datalab track changes | 78.6% |
| 4 | LlamaParse agentic | 75.2% |
| 5 | Reducto | 75.1% |
| 6 | Extend | 74.8% |
| 7 | GPT-6 Astra | 63.3% |
| 8 | Datalab convert | 62.4% |
| 9 | Pulse | 52.7% |
| 10 | Mistral OCR | 43.4% |

These are the independently benchmarked live results as of September 2026. The public runner is for reproduction and extension; it does not claim to reproduce the held-out live leaderboard, which uses 1,500 questions across 94 contracts. See the [leaderboard](https://www.openbenchmarks.dev/document-processing) for full methodology, detailed results, and dated pricing.

## What is public

There are two related datasets:

- [`crosbylegal/RedlineBench`](https://huggingface.co/datasets/crosbylegal/RedlineBench) is the upstream redline-document source. Provenance is pinned to commit `eee1b6790982ed1279e86bec7616b662a61993e6`.
- [`openbenchmarks/OB-LegalQA`](https://huggingface.co/datasets/openbenchmarks/OB-LegalQA) is the runnable public benchmark bundle: 95 questions, tagged and scanned PDFs, and oracle/blind markdown views. Runtime data is pinned to commit `3c7c599d0221adc38f11b3e87c788787077a81fe`.

Both datasets are CC BY 4.0. This repository contains MIT-licensed runner code only; `init` downloads the benchmark assets from Hugging Face and never rerenders the upstream documents.

## Install

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[vendors]'
cp .env.example .env
```

Only the SDKs and credentials for selected parser arms are used. Every run also needs an OpenAI-compatible downstream reader/judge configured through `OPENAI_API_KEY`, or the Azure variables supported in `.env.example`.

## Run

```bash
openbench-document-processing list-workflows

openbench-document-processing init \
  --workflow redline-parsing \
  --split tagged

openbench-document-processing smoke \
  --workflow redline-parsing \
  --split tagged \
  --arms reducto,llamaparse-plus \
  --run-dir runs/my-smoke

openbench-document-processing run \
  --workflow redline-parsing \
  --split tagged \
  --arms all \
  --full \
  --approve-full \
  --approval-id issue-123 \
  --run-dir runs/my-full-run
```

`smoke` selects the same 12 cases every time. `run` uses all 95 public questions and requires an explicit cost acknowledgement plus an audit identifier. Tagged and scanned PDFs are separate splits and never share parse caches.

Resume by running the same command against the same `--run-dir`; completed arms and compatible cached answers are reused. Inspect or re-derive a run with no vendor calls:

```bash
openbench-document-processing watch --workflow redline-parsing --run-dir runs/my-full-run
openbench-document-processing derive-full-run --workflow redline-parsing --run-dir runs/my-full-run
```

## Run artifacts

Each run directory is self-contained:

```text
manifest.json             immutable dataset, split, model, arms and approval
result.json               per-arm scores and per-question verdicts
report.json               machine-readable ranking
report.md                 human-readable ranking
parsed/<split>/           markdown, parser metadata and redacted vendor I/O
answers/<split>/<arm>/    reader request/response and judge decision per case
```

Parser caches are accepted only when both the PDF SHA-256 and the complete parser-settings fingerprint match. API headers and credentials are redacted before vendor exchanges are written.

## Methodology

Every parser receives the same PDF for a split. It renders each contract once, then the same reader model answers every question from that parser's markdown. Exact whole-token matches settle unambiguous answers; residual answers go to a model judge that sees the question and reference answers but not the parser identity.

The primary metric is downstream answer accuracy. The artifacts also retain stale and fused verdicts, parser and reader latency, usage, and estimated cost so results can be audited or recomputed. Reference arms bound the task: `oracle` preserves deleted text as Markdown strikethrough, while `blind` removes the edit distinction.

This benchmark measures whether document ingestion preserves the contract state that a RAG system needs to retrieve and answer correctly. It intentionally holds chunking, embeddings, retrieval, reranking, and the reader fixed so parser differences are not confounded with a different RAG stack.

## Development

```bash
pip install -e '.[dev]'
pytest
```

Tests use fixtures and mocks; CI must never make paid provider calls. Contributions that add or change a provider must pin every output-affecting setting, redact stored requests, and add adapter and cache-invalidation tests.

## License

Code is released under the [MIT License](LICENSE). Dataset assets retain their CC BY 4.0 licenses and attribution requirements.
