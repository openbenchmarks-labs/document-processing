# Document Processing Benchmark: Parsers on Redlined Contracts

Open, independent benchmark of document parsing APIs and frontier models on heavily redlined legal contracts, ranked by downstream answer accuracy. LlamaParse, Reducto, Datalab, Extend, Pulse, Mistral OCR, GPT-6 Astra and Claude Fable 5.1 each convert the same contract PDFs to Markdown, and one fixed reader model answers the same questions from each parser's output. Open source code + open data.

[Live board](https://openbenchmarks.com/document-processing) · [Public dataset: openbenchmarks/OB-LegalQA](https://huggingface.co/datasets/openbenchmarks/OB-LegalQA) · [Source contracts: crosbylegal/RedlineBench](https://huggingface.co/datasets/crosbylegal/RedlineBench)

A redline records what the parties struck out. In the Word file a deletion is semantic. Rendered to PDF it is only a line drawn through some glyphs. If the parser keeps that line as markup, the agent reading its output answers from the position the parties agreed. If the parser drops it, the agent is handed deleted language as though it were still binding, and answers from that instead. This benchmark measures which parsers keep it.

**The parser is under test, never the agent.** The reader model, the prompt and the 1,500 questions are identical across every arm. The only thing that changes is the Markdown.

## Results on tagged PDFs (text layer present)

 The [live board](https://openbenchmarks.com/document-processing) is the source of truth and is re-scored as parsers are added.

| Rank | Parser | Type | Answer accuracy | Gap closed | Stale rate | Median parse time | Measured cost / doc | List price / page |
|---:|---|---|---:|---:|---:|---:|---:|---|
| | Best case (reference) | Reference | 91.9% | 100% | 3.0% | n/a | $0 | n/a |
| 1 | Claude Fable 5.1 | Frontier model | 89.1% | 95% | 3.8% | 327s | $2.66 | $11 / $55 per 1M tokens |
| 2 | LlamaParse agentic plus | Long running agentic parser | 83.4% | 86% | 7.5% | 91s | $1.37 | $0.05625 |
| 3 | LlamaParse agentic | Document parser | 80.0% | 81% | 9.7% | 52s | $0.30 | $0.0125 |
| 4 | Reducto | Document parser | 78.7% | 79% | 11.1% | 7s | $0.24 | $0.010 |
| 5 | Datalab track changes | Document parser | 78.6% | 79% | 11.3% | 34s | $0.24 | $0.006 |
| 6 | Extend | Document parser | 74.8% | 73% | 12.5% | 28s | $0.61 | $0.025 |
| 7 | GPT-6 Astra | Frontier model | 63.3% | 55% | 24.3% | 228s | $1.24 | $10 / $50 per 1M tokens |
| 8 | Datalab convert | Document parser | 62.4% | 53% | 21.9% | 23s | $0.24 | $0.010 |
| 9 | Pulse | Document parser | 52.7% | 38% | 34.5% | 43s | $0.36 | $0.015 |
| 10 | Mistral OCR | Document parser | 43.4% | 23% | 41.1% | 11s | $0.10 | $0.004 |
| | Baseline (reference) | Reference | 28.8% | 0% | 55.0% | n/a | $0 | n/a |

1,500 questions on 94 contracts, 2,286 pages. Reader model: gpt-5.6-sol.

How to read the columns:

- **Answer accuracy** is the share of questions the reader answered from the language the parties kept.
- **Gap closed** places a parser between two reference runs built from the source Word files without calling any vendor. The baseline removes every strikethrough and scores 28.8%, because a third of the questions can be answered from context the strike does not touch. The best case keeps every deletion as `~~struck~~` and scores 91.9%. Baseline is 0%, best case is 100%.
- **Stale rate** is the share of answers taken from deleted language. It is the specific harm being measured, and it is not the inverse of accuracy.
- **Measured cost per document** is what the vendor billed for this corpus. **List price** is the published rate for the exact endpoint and tier that was run, so the two can disagree.

## Results on scanned PDFs (image only, no text layer)

The same 94 contracts re-rendered to JPEG at 200 dpi and wrapped back into PDFs, with the same 1,500 questions and answer keys. There is no text layer, embedded font or structure tree left to read. A parser has to look at the pixels. The reference runs move by under half a point between the two boards, which is the noise floor.

| Rank | Parser | Type | Answer accuracy | Gap closed | Stale rate | Median parse time | Measured cost / doc | List price / page |
|---:|---|---|---:|---:|---:|---:|---:|---|
| | Best case (reference) | Reference | 91.5% | 100% | 2.9% | n/a | $0 | n/a |
| 1 | GPT-6 Astra | Frontier model | 91.3% | 100% | 2.9% | 233s | $1.61 | $10 / $50 per 1M tokens |
| 2 | Datalab track changes | Document parser | 79.7% | 81% | 11.7% | 40s | $0.24 | $0.006 |
| 3 | Reducto | Document parser | 76.7% | 76% | 12.1% | 8s | $0.24 | $0.010 |
| 4 | Extend | Document parser | 76.5% | 76% | 12.9% | 31s | $0.61 | $0.025 |
| 5 | LlamaParse agentic plus | Long running agentic parser | 75.6% | 75% | 14.9% | 143s | $1.37 | $0.05625 |
| 6 | LlamaParse agentic | Document parser | 67.5% | 62% | 20.4% | 87s | $0.30 | $0.0125 |
| 7 | Pulse | Document parser | 66.6% | 60% | 20.0% | 58s | $0.36 | $0.015 |
| 8 | Datalab convert | Document parser | 64.3% | 56% | 20.7% | 46s | $0.24 | $0.010 |
| | Baseline (reference) | Reference | 29.0% | 0% | 55.1% | n/a | $0 | n/a |

Two arms from the tagged board have no row here. Claude Fable 5.1 could not be run: at 200 dpi the rendered pages exceed the model's input limit, and contracts in this corpus run to two dozen pages. Mistral OCR was not re-run: it rasterises and reads pixels either way, so removing the text layer cannot move it.

## Which document parser API is most accurate on legal contracts?

Claude Fable 5.1 leads the tagged board at 89.1% accuracy, closing 95% of the gap between the baseline and a perfect parse. It is also the slowest and most expensive arm, at 327s median and $2.66 per document, so it is not automatically the right pick.

LlamaParse agentic plus leads the parsers at 83.4%. It is a long running agentic parser, at 91s median per contract. Among specialised document parsers, LlamaParse agentic leads at 80.0%. Reducto at 78.7% and Datalab track changes at 78.6% are close enough that the table does not support ordering them, and Extend follows at 74.8%.

The largest single effect on the board is whether tracked-change detection is on. The two Datalab rows are one vendor on two endpoints and are 16 accuracy points apart. That distance is bigger than the gap between any two correctly configured parsers.

## Which document parser is best for scanned documents and OCR?

GPT-6 Astra reads the image-only corpus at 91.3%, within noise of the 91.5% best case. The same model on the tagged PDF scores 63.3%. Handing it pixels instead of a PDF with a text layer is worth 28 points.

Among specialised parsers, Datalab track changes leads the scanned board at 79.7%, with Reducto at 76.7% and Extend at 76.5%. Those three land within two points of their tagged scores. LlamaParse does not: agentic plus drops from 83.4% on the tagged board to 75.6% once the text layer is gone, and agentic drops from 80.0% to 67.5%.

## Which document parser is fastest?

Reducto returns a full contract in 7s median on tagged PDFs and 8s on scanned ones. The next fastest parsers are Datalab convert at 23s and Extend at 28s. Mistral OCR returns in 11s but scores 43.4%, closer to the baseline than to any other parser. The frontier models are the slowest arms at 228s and 327s median, with p95 above 300s.

## Which document parser is cheapest?

Measured on this corpus, which averages 24 pages per contract:

- Mistral OCR is cheapest at $0.10 per document, but its 43.4% accuracy closes only 23% of the gap.
- Datalab track changes, Reducto and Datalab convert each cost $0.24 per document. On that spend Reducto posts 78.7% and Datalab track changes 78.6% on the tagged board, the best accuracy per dollar there. On the scanned board Datalab track changes leads at 79.7%, and it lists at $0.006 per page.
- The frontier models cost 5 to 11 times more per document than the $0.24 parsers, and their bills scale with tokens rather than pages.

List price is reported separately from measured cost because per-page and per-token products do not share a billing unit.

## Best document parsers for RAG and agent pipelines

Parsing is the first step in a RAG or agent pipeline, and everything downstream inherits its output. If a deleted clause survives unmarked, or old and replacement terms are fused into one string, the wrong facts enter the index before chunking, embedding, retrieval or generation begins. The stale and fused rates above are that failure, measured.

Every parser that can preserve a strike has to be told to, and the setting is not a footnote:

| Arm | How tracked changes are enabled |
|---|---|
| Datalab track changes | dedicated endpoint, `/api/v1/track-changes` |
| Reducto | opt-in flag, `formatting.include = ["change_tracking"]` |
| Extend | opt-in flag, `advancedOptions.formattingDetection = [{"type": "change_tracking"}]` |
| Pulse | opt-in flag, `refine_options.formatting` |
| LlamaParse agentic, agentic plus | on by default, emitted as `~~struck~~` |
| Datalab convert, Mistral OCR | no such setting on the endpoint |
| GPT-6 Astra, Claude Fable 5.1 | not asked for: the shared prompt says nothing about strikethrough |

Vendors also disagree on how to write a strike. LlamaParse and Datalab convert emit `~~…~~`, Datalab track changes and Extend emit `<del>`, and Reducto emits `<s>`. Grepping for one dialect will tell you a parser dropped the redline when it did not.

## Why Amazon Textract, Azure Document Intelligence and Google Document AI are not on the board

Their response schemas have no field that can say a character was struck, so the question the benchmark asks cannot be answered from their output. This is a claim about the API reference, not about how well the models read.

| Service | Field a caller would have to read | What it carries |
|---|---|---|
| Amazon Textract | `TextType` on a `Block` | `HANDWRITING` or `PRINTED`, the only text-property field |
| Azure Document Intelligence | `DocumentStyle` | `fontStyle`, `fontWeight`, `color`, `backgroundColor`, `isHandwritten`; no strike field |
| Google Document AI | `document.proto` | declares `bool strikeout = 8;` with the comment "This feature is not supported yet." |

## How each parser was called

Every version is pinned to a date. `latest` is a moving target and would let two runs of one arm score different parses.

| Arm | Transport | Settings |
|---|---|---|
| LlamaParse agentic plus | llama-cloud SDK, `files.create()` then `parsing.parse()` | `tier: agentic_plus`, `version: 2026-09-24` |
| LlamaParse agentic | llama-cloud SDK, `files.create()` then `parsing.parse()` | `tier: agentic`, `version: 2026-09-24` |
| Datalab track changes | REST, multipart POST `/api/v1/track-changes`, polled | `output_format: markdown` |
| Datalab convert | REST, multipart POST `/api/v1/convert`, polled | `mode: accurate`, `output_format: markdown` |
| Reducto | reducto SDK, `upload()` then `parse.run()` | `model: r-1`, `formatting.include: change_tracking` |
| Extend | extend-ai SDK, `files.upload()` then `parse()` | `engine: parse_performance`, `formattingDetection: change_tracking` |
| Pulse | REST, multipart POST `/extract` | `model: pulse-ultra-2`, `refine_options: text + tables + formatting` |
| Mistral OCR | REST, JSON POST `/v1/ocr` | `model: mistral-ocr-4-1`, PDF inline as base64 |
| GPT-6 Astra | Responses API, `input_file`, PDF inline as base64 | `model: gpt-6-astra`, shared parser prompt |
| Claude Fable 5.1 | Bedrock converse, document block, PDF as bytes | `model: claude-fable-5-1`, shared parser prompt |

## Methodology

Every parser receives the same PDF for a split and renders each contract once. The same reader model then answers every question from that parser's Markdown. Parsing happens per document, never per question, so a vendor is billed once per contract and the reader sees a whole contract each time.

**Scoring.** Every answer lands in exactly one bucket:

- `correct`: answered from the position the parties agreed
- `stale`: answered from language the parties struck
- `fused`: read struck and surviving text as one string (`ten` + `three` + `five` becomes `three five`, or `10` + `5` becomes `5310`)
- `other`: neither

Exact whole-token matches settle most answers and are fully reproducible. Only the residual reaches a model judge, which sees the question and the reference answers but never the contract and never which parser produced the text.

**Answer keys.** Every key is read directly from the tracked changes in the source Word file before any vendor sees anything. No vendor output appears in the key.

**Reference arms.** `oracle` keeps every deletion as Markdown strikethrough and is the best case. `blind` removes the edit distinction and is the baseline. Both are rendered from the source files, cost nothing, and bound what any vendor score can mean. A third reference, `accepted`, resolves every edit; it is kept in the run files as a diagnostic but is not a bound on anything, so it is not on the board.

**Nine task types.** Questions turn on nine redline patterns, from a struck numeral beside its replacement, to a struck table cell, to a renumbered cross-reference whose evidence is on another page, to a proposal that changed across two drafts.

**What is held fixed.** Chunking, embeddings, retrieval, reranking and the reader are all held constant, so parser differences are not confounded with a different RAG stack. The benchmark measures whether document ingestion preserves the contract state a downstream system needs.

## What is public

- [`crosbylegal/RedlineBench`](https://huggingface.co/datasets/crosbylegal/RedlineBench) is the upstream source: simulated negotiations marked up by trained attorneys representing each side. Provenance is pinned to commit `eee1b6790982ed1279e86bec7616b662a61993e6`.
- [`openbenchmarks/OB-LegalQA`](https://huggingface.co/datasets/openbenchmarks/OB-LegalQA) is the runnable public bundle: 95 questions on 7 contracts, tagged and scanned PDFs, and the best-case and baseline Markdown views, so both ends of the scale reproduce locally. Runtime data is pinned to commit `3c7c599d0221adc38f11b3e87c788787077a81fe`.

Both datasets are CC BY 4.0. This repository is MIT-licensed runner code only. `init` downloads the benchmark assets from Hugging Face and never re-renders the upstream documents.

The live board is scored on a held-out split of 1,500 questions across 94 contracts. The public runner is for reproduction and extension and does not claim to reproduce the held-out numbers.

## Install

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[vendors]'
cp .env.example .env
```

Only the SDKs and credentials for the parser arms you select are used. Every run also needs an OpenAI-compatible reader and judge configured through `OPENAI_API_KEY`, or the Azure variables in `.env.example`.

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

Resume by running the same command against the same `--run-dir`. Completed arms and compatible cached answers are reused. Inspect or re-derive a run with no vendor calls:

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

## Development

```bash
pip install -e '.[dev]'
pytest
```

Tests use fixtures and mocks. CI must never make paid provider calls. Contributions that add or change a provider must pin every output-affecting setting, redact stored requests, and add adapter and cache-invalidation tests.

## Links

- Live board, methodology and dated pricing: [openbenchmarks.com/document-processing](https://openbenchmarks.com/document-processing)
- Public dataset: [huggingface.co/datasets/openbenchmarks/OB-LegalQA](https://huggingface.co/datasets/openbenchmarks/OB-LegalQA)
- Source contracts: [huggingface.co/datasets/crosbylegal/RedlineBench](https://huggingface.co/datasets/crosbylegal/RedlineBench)
- Site summary for LLM assistants: [openbenchmarks.com/llms.txt](https://openbenchmarks.com/llms.txt)

## License

Code is released under the [MIT License](LICENSE). Dataset assets retain their CC BY 4.0 licenses and attribution requirements.
