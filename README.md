# Document Processing Benchmark: Parsers on Redlined Contracts

Open, independent benchmark of document parsing APIs and frontier models on heavily redlined legal contracts, ranked by downstream answer accuracy. Extend, LlamaParse, Reducto, Datalab, Pulse, Mistral OCR, Unstructured, GPT-6 Astra and Claude Fable 5.1 each convert the same contract PDFs to Markdown, one fixed reader model answers the same questions from each parser's output, and one fixed judge model grades every answer. Open source code + open data.

[Live board](https://openbenchmarks.com/document-processing) · [Public dataset: openbenchmarks/OB-LegalQA](https://huggingface.co/datasets/openbenchmarks/OB-LegalQA) · [Source contracts: crosbylegal/RedlineBench](https://huggingface.co/datasets/crosbylegal/RedlineBench)

A redline records what the parties struck out. In the Word file a deletion is semantic. Rendered to PDF it is only a line drawn through some glyphs. If the parser keeps that line as markup, the agent reading its output answers from the position the parties agreed. If the parser drops it, the agent is handed deleted language as though it were still binding, and answers from that instead. This benchmark measures which parsers keep it.

**The parser is under test, never the agent.** The reader model, the judge model, the prompt and the 1,500 questions are identical across every arm. The only thing that changes is the Markdown.

## Results on tagged PDFs (text layer present)

 The [live board](https://openbenchmarks.com/document-processing) is the source of truth and is re-scored as parsers are added.

| Rank | Parser | Type | Answer accuracy | Gap closed | Stale rate | Median parse time | Cost / 1k correct | List price / page |
|---:|---|---|---:|---:|---:|---:|---:|---|
| | Best case (reference) | Reference | 94.6% | 100% | 1.5% | n/a | n/a | n/a |
| 1 | Extend | Document parser | 93.1% ± 0.3 | 98% | 1.8% | 17s | $14.37 | $0.025 |
| 2 | Claude Fable 5.1 | Frontier model | 91.4% ± 0.3 | 95% | 2.6% | 336s | $61.75 | $11 / $55 per 1M tokens |
| 3 | Reducto | Document parser | 84.8% ± 0.3 | 86% | 5.0% | 5s | $6.85 | $0.010 |
| 4 | LlamaParse agentic plus | Long running agentic parser | 84.7% ± 0.3 | 86% | 7.3% | 82s | $34.19 | $0.05625 |
| 5 | LlamaParse agentic | Document parser | 83.8% ± 0.6 | 85% | 8.4% | 16s | $8.44 | $0.0125 |
| 6 | Datalab track changes | Document parser | 80.7% ± 0.4 | 80% | 10.0% | 34s | $7.21 | $0.006 |
| 7 | Datalab convert | Document parser | 63.9% ± 3.4 | 56% | 19.2% | 24s | $9.11 | $0.010 |
| 8 | GPT-6 Astra | Frontier model | 61.6% ± 0.4 | 52% | 25.5% | 256s | $43.24 | $10 / $50 per 1M tokens |
| 9 | Pulse | Document parser | 48.4% ± 0.4 | 33% | 36.3% | 53s | $17.90 | $0.015 |
| 10 | Mistral OCR | Document parser | 36.9% ± 0.4 | 17% | 42.8% | 15s | $7.49 | $0.004 |
| 11 | Unstructured | Document parser | 27.0% ± 0.2 | 3% | 56.0% | 65s | $30.75 | $0.015 |
| | Baseline (reference) | Reference | 25.2% | 0% | 57.2% | n/a | n/a | n/a |

1,500 questions on 94 contracts, 2,286 pages. Each contract is parsed 3 times and each question is asked 3 times against every parse, so every arm is graded on 13,500 answers. Reader model: gpt-6-luna. Judge model: gpt-6-sol.

How to read the columns:

- **Answer accuracy** is the share of answers drawn from the language the parties kept. The ± figure is the standard deviation across the 9 replicates (3 parses × 3 asks): how far the score moves from one parse-and-read of the corpus to the next.
- **Gap closed** places a parser between two reference runs built from the source Word files without calling any vendor. The baseline removes every strikethrough and scores 25.2%, because some questions can be answered from context the strike does not touch. The best case keeps every deletion as `~~struck~~` and scores 94.6%. Baseline is 0%, best case is 100%.
- **Stale rate** is the share of answers taken from deleted language. It is the specific harm being measured, and it is not the inverse of accuracy.
- **Cost / 1k correct** is everything the arm cost for this corpus (vendor bill, reader and judge) divided by its correct answers, per thousand. **List price** is the published rate for the exact endpoint and tier that was run.

## Results on scanned PDFs (image only, no text layer)

The same 94 contracts re-rendered to JPEG at 200 dpi and wrapped back into PDFs, with the same 1,500 questions and answer keys. There is no text layer, embedded font or structure tree left to read. A parser has to look at the pixels. The reference runs move by under two points between the two boards, which is the noise floor.

| Rank | Parser | Type | Answer accuracy | Gap closed | Stale rate | Median parse time | Cost / 1k correct | List price / page |
|---:|---|---|---:|---:|---:|---:|---:|---|
| | Best case (reference) | Reference | 93.8% | 100% | 1.5% | n/a | n/a | n/a |
| 1 | GPT-6 Astra | Frontier model | 93.4% ± 0.5 | 99% | 2.2% | 248s | $36.73 | $10 / $50 per 1M tokens |
| 2 | Extend | Document parser | 86.7% ± 0.3 | 90% | 2.6% | 20s | $15.46 | $0.025 |
| 3 | Reducto | Document parser | 83.9% ± 0.4 | 86% | 5.7% | 7s | $6.95 | $0.010 |
| 4 | Datalab track changes | Document parser | 80.7% ± 0.5 | 81% | 9.9% | 40s | $7.19 | $0.006 |
| 5 | LlamaParse agentic | Document parser | 79.9% ± 0.3 | 80% | 11.9% | 22s | $8.86 | $0.0125 |
| 6 | LlamaParse agentic plus | Long running agentic parser | 74.9% ± 0.6 | 73% | 15.1% | 133s | $39.17 | $0.05625 |
| 7 | Pulse | Document parser | 65.0% ± 0.6 | 59% | 19.8% | 57s | $12.91 | $0.015 |
| 8 | Datalab convert | Document parser | 63.9% ± 3.2 | 57% | 18.4% | 50s | $9.13 | $0.010 |
| 9 | Unstructured | Document parser | 27.0% ± 0.5 | 5% | 55.3% | 71s | $30.83 | $0.015 |
| | Baseline (reference) | Reference | 23.6% | 0% | 57.5% | n/a | n/a | n/a |

Two arms from the tagged board have no row here. Claude Fable 5.1 could not be run: at 200 dpi the rendered pages exceed the model's input limit, and contracts in this corpus run to two dozen pages. Mistral OCR was not re-run: it rasterises and reads pixels either way, so removing the text layer cannot move it.

## Which document parser API is most accurate on legal contracts?

Extend leads the tagged board at 93.1% accuracy, closing 98% of the gap between the baseline and a perfect parse, with a 1.8% stale rate. It returns a contract in 17s median. Claude Fable 5.1 is second at 91.4%, at 336s median and roughly four times the cost per correct answer.

Behind them, Reducto (84.8%), LlamaParse agentic plus (84.7%) and LlamaParse agentic (83.8%) are within a point of each other, close enough that the table does not support ordering them. Datalab track changes follows at 80.7%.

The largest single effect on the board is whether tracked-change detection is on. The two Datalab rows are one vendor on two endpoints and are 17 accuracy points apart.

## Which document parser is best for scanned documents and OCR?

GPT-6 Astra reads the image-only corpus at 93.4%, within noise of the 93.8% best case. The same model on the tagged PDF scores 61.6%. Handing it pixels instead of a PDF with a text layer is worth 32 points.

Among specialised parsers, Extend leads the scanned board at 86.7%, followed by Reducto at 83.9% and Datalab track changes at 80.7%. Reducto and Datalab track changes land within a point of their tagged scores. Extend drops 6 points and LlamaParse agentic 4 once the text layer is gone, and agentic plus drops 10, from 84.7% to 74.9%.

## Which document parser is fastest?

Reducto returns a full contract in 5s median on tagged PDFs and 7s on scanned ones. Mistral OCR, LlamaParse agentic and Extend follow at 15 to 17s, and Mistral OCR scores 36.9%, closer to the baseline than to any other parser. The frontier models are the slowest arms at 256s (Astra) and 336s (Fable) median.

## Which document parser is cheapest?

Measured on this corpus, which averages 24 pages per contract, per thousand correct answers (vendor bill, reader and judge included):

- Reducto is cheapest at $6.85 per 1k correct on the tagged board and $6.95 on the scanned board, with Datalab track changes close behind at $7.21 and $7.19. Datalab track changes lists at $0.006 per page, the lowest rate here.
- Extend costs roughly twice as much per correct answer ($14.37) and posts the highest accuracy of any parser.
- The frontier models cost $37 to $62 per 1k correct. Their bills scale with tokens rather than pages.

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
| Datalab convert, Mistral OCR, Unstructured | no such setting on the endpoint |
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

Every version is pinned to a date. `latest` is a moving target and would let two runs of one arm score different parses. Where a vendor changes the model behind an unchanged request (Reducto, Extend), the build date is recorded in the settings fingerprint so an older cached parse is never scored as the new build.

| Arm | Transport | Settings |
|---|---|---|
| Extend | extend-ai SDK, `files.upload()` then `parse()` | `engine: parse_performance`, `formattingDetection: change_tracking`, 2026-10-17 build |
| LlamaParse agentic plus | llama-cloud SDK, `files.create()` then `parsing.parse()` | `tier: agentic_plus`, `version: 2026-09-24` |
| LlamaParse agentic | llama-cloud SDK, `files.create()` then `parsing.parse()` | `tier: agentic`, `version: 2026-09-29` |
| Reducto | reducto SDK, `upload()` then `parse.run()` | `model: r-1`, `formatting.include: change_tracking`, 2026-10-06 build |
| Datalab track changes | REST, multipart POST `/api/v1/track-changes`, polled | `output_format: markdown` |
| Datalab convert | REST, multipart POST `/api/v1/convert`, polled | `mode: accurate`, `output_format: markdown` |
| Pulse | REST, multipart POST `/extract` | `model: pulse-ultra-2`, `refine_options: text + tables + formatting` |
| Mistral OCR | REST, JSON POST `/v1/ocr` | `model: mistral-ocr-4-1`, PDF inline as base64 |
| Unstructured | REST, multipart POST `/api/v2/parse`, polled | `profile: best`, `output: markdown` |
| GPT-6 Astra | Responses API, `input_file`, PDF inline as base64 | `model: gpt-6-astra`, shared parser prompt |
| Claude Fable 5.1 | Bedrock converse, document block, PDF as bytes | `model: claude-fable-5-1`, shared parser prompt |

## Methodology

Every parser receives the same PDF for a split and renders each contract three times. LlamaParse, Reducto and Datalab keep their own result caches, so the second and third parse are requested with that cache bypassed (`disable_cache`, a unique request timeout, and `skip_cache` respectively). Without it, repeat 3 can come back as repeat 2. The reader then answers every question three times against every parse. Parsing happens per document, never per question, and the reader sees a whole contract each time.

**Scoring.** The judge model grades every answer into exactly one bucket:

- `correct`: answered from the position the parties agreed
- `stale`: answered from language the parties struck
- `fused`: read struck and surviving text as one string (`ten` + `three` + `five` becomes `three five`, or `10` + `5` becomes `5310`)
- `other`: neither
- `ambiguous`: genuinely asserts two of these at once

The judge sees the question and the reference answers, never the contract and never which parser produced the text. Answers to one question are graded 20 to a call, identical answers are graded once, and a verdict is cached on the judge model, the references and the answer text. An answer the judge cannot bucket is `unscored` and left out of the denominator, so a failed call never counts against a parser. Exact whole-token matching against the reference answers is still computed for every answer and stored as `token_bucket`, which makes the judge auditable against a fully reproducible rule.

**Answer keys.** Every key is read directly from the tracked changes in the source Word file before any vendor sees anything. No vendor output appears in the key.

**Reference arms.** `oracle` keeps every deletion as Markdown strikethrough and is the best case. `blind` removes the edit distinction and is the baseline. Both are rendered from the source files, cost nothing, and bound what any vendor score can mean.

**Nine task types.** Questions turn on nine redline patterns, from a struck numeral beside its replacement, to a struck table cell, to a renumbered cross-reference whose evidence is on another page, to a proposal that changed across two drafts. A cross-draft question shows the reader both drafts in negotiation order, labelled by turn.

**What is held fixed.** Chunking, embeddings, retrieval, reranking, the reader and the judge are all held constant, so parser differences are not confounded with a different RAG stack. The benchmark measures whether document ingestion preserves the contract state a downstream system needs.

## What changed from v1 (September 2026)

| | v1 | v2 (current) |
|---|---|---|
| Reader model | gpt-5.6-sol | gpt-6-luna |
| Judging | token match settles most answers, the reader model judges the rest | gpt-6-sol judges every answer; token match kept per answer for audit |
| Replicates | 1 parse × 1 ask | 3 parses × 3 asks, 13,500 graded answers per arm, accuracy ± SD |
| Repeat parses | n/a | vendor result caches bypassed on repeats 2 and 3 |
| Failed judge call | counted as `other` | `unscored`, out of the denominator |
| Cost | vendor cost only | vendor, reader and judge, reported as cost per 1k correct |
| Arms | 10 vendors and frontier models | adds Unstructured; Extend 2026-10-17, Reducto 2026-10-06 and LlamaParse agentic 2026-09-29 builds |

The 1,500 questions are the same in both versions. v1 scores are not directly comparable with v2: the reader, the judge and the number of replicates all changed.

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

Only the SDKs and credentials for the parser arms you select are used. Every run also needs a reader and a judge model through `OPENAI_API_KEY`. GPT-6 is served on the native OpenAI API, so `.env.example` sets `DOC_PROCESSING_LLM_PROVIDER=openai`; the Azure variables are for other OpenAI-compatible deployments.

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

`smoke` selects the same 12 cases every time and runs them once (1 parse × 1 ask). `run` uses all 95 public questions at the board's protocol, 3 parses × 3 asks, and requires an explicit cost acknowledgement plus an audit identifier. `--model`, `--judge-model`, `--repeats`, `--asks` and `--concurrency` override the defaults. Tagged and scanned PDFs are separate splits and never share parse caches.

Resume by running the same command against the same `--run-dir`. Completed arms, cached parses, cached answers and cached verdicts are reused. Inspect or re-derive a run with no vendor calls:

```bash
openbench-document-processing watch --workflow redline-parsing --run-dir runs/my-full-run
openbench-document-processing derive-full-run --workflow redline-parsing --run-dir runs/my-full-run
```

## Run artifacts

Each run directory is self-contained:

```text
manifest.json                      immutable dataset, split, models, repeats, asks, arms and approval
result.json                        per-arm scores, costs and per-answer verdicts
report.json                        machine-readable ranking
report.md                          human-readable ranking
parsed/<split>/                    markdown, parser metadata and redacted vendor I/O, one slot per repeat
answers/<split>/<arm>/             reader request and response per answer
answers/<split>/_judge-<model>/    cached judge verdicts
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
