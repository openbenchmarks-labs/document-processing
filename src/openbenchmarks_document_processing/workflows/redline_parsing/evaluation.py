from __future__ import annotations

import json
import re
import statistics
import time

from .environment import usage_of

LABELS = ("correct", "stale", "fused")
SCORED = (*LABELS, "other", "ambiguous")

# The judge buckets every answer. Token matching is still computed per row as
# `token_bucket`, so the judge can be audited against a fully reproducible rule,
# but it no longer decides any score.
#
# batch-v2: a first judge marked answers wrong for naming a live replacement
# clause when the reference explanation said the old clause was deleted "without
# replacement". v2 grades the answer to the question, and only lets extra detail
# count against it when that detail contradicts the correct reference or presents
# the struck language as operative.
BATCH_VERSION = "batch-v2"
BATCH_SIZE = 20

SYSTEM = (
    "You bucket answers about a contract that carried tracked changes. For each "
    "answer, decide which reference it actually agrees with. Reply with JSON only."
)
PROMPT = """Question:
{question}

Correct answer (what the parties agreed):
{correct}

Stale answer (language the parties struck out):
{stale}

Fused answer (struck and surviving text read as one string):
{fused}

Answers to bucket, as a JSON list:
{answers}

How to bucket each answer:
- Grade the answer's answer to the question. "correct" means its conclusion
  agrees with the correct answer above.
- "stale" means it treats the struck language as operative; "fused" means it
  reads struck and surviving text as one string.
- The reference explanations describe the change the question is about. The
  contract may contain other live provisions, including replacement clauses,
  that the references do not mention. An answer that names such a provision is
  not wrong for doing so. Extra detail only counts against an answer when it
  contradicts the correct answer or presents the stale language as operative.
- Use "ambiguous" only when an answer genuinely asserts two of these at once,
  not when you are merely unsure. Use "other" when it agrees with none of them.

Reply with JSON: {{"verdicts": [{{"id": "<id>", "bucket": "correct|stale|fused|other|ambiguous", "why": "one short clause"}}]}}
with exactly one verdict per id above, each bucketed on its own."""


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def token_match(needle: str, haystack: str) -> bool:
    pattern = rf"(?<![\w%])(?<!\d\.){re.escape(needle)}(?!\.\d)(?![\w%])"
    return re.search(pattern, haystack, re.I) is not None


def classify(answer: str, match: dict) -> str:
    """The token-match bucket: kept per row to audit the judge, never scored."""
    hits = {label for label in LABELS for token in (match.get(label) or [])
            if token_match(token, answer)}
    if not hits:
        return "other"
    return hits.pop() if len(hits) == 1 else "ambiguous"


def references(case) -> dict:
    match = case.match or {}
    return {
        "question": case.question,
        "correct": case.expected_answer + (f" -- {case.expected_detail}"
                                           if case.expected_detail else ""),
        "stale": " | ".join(match.get("stale") or []) or "(none recorded)",
        "fused": " | ".join(match.get("fused") or []) or "(none recorded)",
    }


def parse_verdicts(text: str, ids: list[str]) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """(verdicts by id, ids still needing one). Unknown ids are ignored, a
    repeated id counts only if every copy agrees, and a bucket outside the set
    is treated as no verdict rather than guessed at."""
    wanted = set(ids)
    try:
        payload = json.loads(re.search(r"\{.*\}", text or "", re.S).group(0))
        entries = payload.get("verdicts") or []
    except Exception:  # noqa: BLE001 - an unreadable reply is simply no verdicts
        return {}, list(ids)
    seen: dict[str, list[tuple[str, str]]] = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("id") or "")
        bucket = str(entry.get("bucket") or "")
        if item_id in wanted and bucket in SCORED:
            seen.setdefault(item_id, []).append((bucket, str(entry.get("why") or "")[:200]))
    verdicts = {i: v[0] for i, v in seen.items() if len({b for b, _ in v}) == 1}
    return verdicts, [i for i in ids if i not in verdicts]


def judge_batch(client, model: str, refs: dict,
                items: list[tuple[str, str]]) -> tuple[dict[str, tuple[str, str]], list[str], dict]:
    """Bucket up to a batch of answers to one question in one call.

    Returns (verdicts by id, ids without a usable verdict, hop). The question and
    its references are sent once per call rather than once per answer."""
    ids = [item_id for item_id, _ in items]
    answers = json.dumps([{"id": item_id, "answer": norm_ws(text)[:4000] or "(empty)"}
                          for item_id, text in items], ensure_ascii=False)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": PROMPT.format(answers=answers, **refs)}]
    started = time.time()
    response = client.responses.create(model=model, input=messages)
    text = (response.output_text or "").strip()
    hop = {"request": {"model": model, "input": messages},
           "response": {"output_text": text, "usage": usage_of(response),
                        "seconds": round(time.time() - started, 2)}}
    verdicts, missing = parse_verdicts(text, ids)
    return verdicts, missing, hop


def _rates(rows: list[dict]) -> dict:
    scored = [r for r in rows if r.get("bucket") in SCORED]
    counts = {bucket: sum(1 for r in scored if r["bucket"] == bucket) for bucket in SCORED}
    total = len(scored) or 1
    return {"n": len(scored), "buckets": counts,
            "accuracy": counts["correct"] / total,
            "stale_rate": counts["stale"] / total,
            "fused_rate": counts["fused"] / total}


def score(rows: list[dict]) -> dict:
    """Board numbers for one arm.

    Only judged rows count. A row the judge could not bucket is `unscored`: it
    says nothing about the parser, so it is left out of the denominator and
    reported as a count instead of being counted wrong.

    With several (parse repeat, ask) rows per question, the rates are over all of
    them, and each (repeat, ask) pair is also scored as a board of its own.
    `accuracy_sd` is the sample SD of those replicate scores: how far the number
    moves between one parse-and-read of the corpus and the next, parser noise
    and reader noise together.
    """
    out = _rates(rows)
    out["rows"] = len(rows)
    out["unscored"] = sum(1 for r in rows if r.get("bucket") not in SCORED)
    cells: dict[tuple[int, int], list[dict]] = {}
    for row in rows:
        cells.setdefault((row.get("repeat") or 1, row.get("ask") or 1), []).append(row)
    if len(cells) > 1:
        replicates = {f"r{r}a{a}": _rates(cell) for (r, a), cell in sorted(cells.items())}
        for field in ("accuracy", "stale_rate", "fused_rate"):
            values = [rep[field] for rep in replicates.values() if rep["n"]]
            out[f"{field}_sd"] = statistics.stdev(values) if len(values) > 1 else 0.0
        out["replicates"] = {k: round(v["accuracy"], 4) for k, v in replicates.items()}
    return out
