from __future__ import annotations

import json
import re
import time

from .environment import usage_of

LABELS = ("correct", "stale", "fused")
SYSTEM = (
    "You bucket an answer about a contract that carried tracked changes. "
    "Decide which reference the answer agrees with. Reply with JSON only."
)
PROMPT = """Question: {question}

Correct answer: {correct}
Stale answer: {stale}
Fused answer: {fused}
Answer to bucket: {answer}

Reply with JSON: {{"bucket":"correct|stale|fused|other|ambiguous","why":"one short clause"}}"""


def token_match(needle: str, haystack: str) -> bool:
    pattern = rf"(?<![\w%])(?<!\d\.){re.escape(needle)}(?!\.\d)(?![\w%])"
    return re.search(pattern, haystack, re.I) is not None


def classify(answer: str, match: dict) -> str:
    hits = {label for label in LABELS for token in (match.get(label) or [])
            if token_match(token, answer)}
    if not hits:
        return "other"
    return hits.pop() if len(hits) == 1 else "ambiguous"


def judge(client, model: str, case, answer: str) -> tuple[str, str, dict]:
    prompt = PROMPT.format(
        question=case.question,
        correct=case.expected_answer + (f" — {case.expected_detail}" if case.expected_detail else ""),
        stale=" | ".join(case.match.get("stale") or []) or "(none)",
        fused=" | ".join(case.match.get("fused") or []) or "(none)",
        answer=re.sub(r"\s+", " ", answer).strip()[:4000] or "(empty)",
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    started = time.time()
    response = client.responses.create(model=model, input=messages)
    text = (response.output_text or "").strip()
    found = re.search(r"\{.*\}", text, re.S)
    payload = json.loads(found.group(0)) if found else {}
    bucket = str(payload.get("bucket") or "other")
    if bucket not in (*LABELS, "other", "ambiguous"):
        bucket = "other"
    hop = {"request": {"model": model, "input": messages},
           "response": {"output_text": text, "usage": usage_of(response),
                        "seconds": round(time.time() - started, 2)}}
    return bucket, str(payload.get("why") or "")[:200], hop


def score(rows: list[dict]) -> dict:
    total = len(rows) or 1
    counts = {label: sum(row.get("bucket") == label for row in rows)
              for label in (*LABELS, "other", "ambiguous")}
    return {"n": len(rows), "buckets": counts,
            "accuracy": counts["correct"] / total,
            "stale_rate": counts["stale"] / total,
            "fused_rate": counts["fused"] / total}
