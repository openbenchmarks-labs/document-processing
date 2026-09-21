from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from . import evaluation, pricing, providers
from .dataset import Case, Document, view_for
from .environment import usage_of
from .storage import atomic_json, cache_key, load_cached

SYSTEM = (
    "You answer questions about a contract using only the document text given. "
    "The text may contain edit markup. Answer in one short sentence."
)
PROMPT = """{markdown}

---
Question: {question}
Answer in one short sentence, quoting the operative language where it helps."""
EXPLICIT_CACHE_FAMILIES = ("gpt-5.6", "gpt-6")


def ask(client, model: str, markdown: str, question: str, prefix_key: str) -> tuple[str, dict]:
    tail = PROMPT.format(markdown="", question=question)
    extra: dict = {"prompt_cache_key": prefix_key}
    if model.startswith(EXPLICIT_CACHE_FAMILIES):
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": [
            {"type": "input_text", "text": markdown,
             "prompt_cache_breakpoint": {"mode": "explicit"}},
            {"type": "input_text", "text": tail},
        ]}]
        extra["prompt_cache_options"] = {"mode": "explicit"}
    else:
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": markdown + tail}]
    started = time.time()
    response = client.responses.create(model=model, input=messages, **extra)
    text = (response.output_text or "").strip()
    return text, {"request": {"model": model, "question": question,
                              "markdown_chars": len(markdown), "prompt_cache_key": prefix_key},
                  "response": {"output_text": text, "usage": usage_of(response),
                               "seconds": round(time.time() - started, 2)}}


def run_arm(arm: str, cases: list[Case], documents: dict[str, Document], client,
            model: str, run_dir: Path, split: str) -> dict:
    parse_cache = run_dir / "parsed" / split
    answers_dir = run_dir / "answers" / split / arm
    rendered: dict[str, str] = {}
    parse_meta: list[dict] = []
    parse_cost: dict[str, dict] = {}
    wanted = sorted({doc for case in cases for doc in case.documents})
    for index, document_id in enumerate(wanted, 1):
        markdown, meta = providers.render(documents[document_id], arm, parse_cache)
        rendered[document_id] = markdown
        cost = pricing.cost_of_parse(arm, meta)
        parse_cost[document_id] = cost
        parse_meta.append({"document_id": document_id, "cost": cost, **meta})
        print(f"[{arm}] parsed {index}/{len(wanted)} {document_id}", flush=True)

    questions_per_doc: dict[str, int] = defaultdict(int)
    for case in cases:
        for document_id in case.documents:
            questions_per_doc[document_id] += 1

    rows: list[dict] = []
    for index, case in enumerate(cases, 1):
        markdown = view_for(case, documents, rendered)
        key = cache_key(model, SYSTEM, PROMPT, evaluation.SYSTEM, evaluation.PROMPT,
                        case.question, case.expected_answer,
                        json.dumps(case.match, sort_keys=True), markdown)
        answer_path = answers_dir / f"{case.id}.json"
        cached = load_cached(answer_path, key)
        if cached:
            rows.append({**cached["row"], "reused": True})
            if index % 10 == 0 or index == len(cases):
                print(f"[{arm}] answered {index}/{len(cases)}", flush=True)
                atomic_json(run_dir / "progress.json", {
                    "arm": arm, "status": "running", "cases_complete": index,
                    "cases_total": len(cases)})
            continue
        else:
            text, ask_hop = ask(client, model, markdown, case.question,
                                f"{arm}:{'+'.join(sorted(case.documents))}")
        bucket = evaluation.classify(text, case.match)
        judge_hop = None
        why = ""
        if bucket in ("other", "ambiguous"):
            bucket, why, judge_hop = evaluation.judge(client, model, case, text)
        row = {"id": case.id, "task_type": case.task_type, "documents": case.documents,
               "answer": text, "bucket": bucket, "judge_why": why,
               "usage": ask_hop.get("response", {}).get("usage") or {},
               "llm_seconds": ask_hop.get("response", {}).get("seconds"),
               "reused": bool(cached)}
        atomic_json(answer_path, {"key": key, "answer": text, "ask": ask_hop,
                                  "judge": judge_hop, "row": row})
        rows.append(row)
        if index % 10 == 0 or index == len(cases):
            print(f"[{arm}] answered {index}/{len(cases)}", flush=True)
            atomic_json(run_dir / "progress.json", {
                "arm": arm, "status": "running", "cases_complete": index,
                "cases_total": len(cases)})

    vendor_usd = sum((item.get("usd") or 0) for item in parse_cost.values())
    llm_usd = sum((pricing.cost_of_llm(model, row["usage"]).get("usd") or 0) for row in rows)
    return {"arm": arm, **providers.identity(arm), "score": evaluation.score(rows),
            "cost": {"vendor_usd": round(vendor_usd, 6), "llm_usd": round(llm_usd, 6)},
            "documents": parse_meta, "rows": rows}


def derive(run_dir: Path) -> dict:
    result_path = run_dir / "result.json"
    if not result_path.is_file():
        raise SystemExit(f"missing {result_path}")
    result = json.loads(result_path.read_text())
    rows = []
    accuracies = {arm["arm"]: evaluation.score(arm.get("rows") or [])["accuracy"]
                  for arm in result.get("arms", [])}
    floor, ceiling = accuracies.get("blind"), accuracies.get("oracle")
    for arm in result.get("arms", []):
        score = evaluation.score(arm.get("rows") or [])
        arm["score"] = score
        parse_seconds = sorted(float(doc.get("seconds") or 0) for doc in arm.get("documents", [])
                               if doc.get("seconds") is not None)
        median = _percentile(parse_seconds, 0.5)
        p95 = _percentile(parse_seconds, 0.95)
        gap = None
        if floor is not None and ceiling is not None and ceiling != floor:
            gap = round((score["accuracy"] - floor) / (ceiling - floor), 8)
        rows.append({"arm": arm["arm"], "accuracy": score["accuracy"],
                     "stale_rate": score["stale_rate"], "n": score["n"],
                     "gap_closed": gap, "median_seconds": median, "p95_seconds": p95,
                     "vendor_usd": arm.get("cost", {}).get("vendor_usd")})
    rows.sort(key=lambda item: (-item["accuracy"], item["arm"]))
    report = {"workflow": result["workflow"], "dataset": result["dataset"],
              "split": result["split"], "model": result["model"], "ranking": rows}
    atomic_json(run_dir / "report.json", report)
    lines = ["# Redline parsing benchmark", "",
             f"Dataset: `{result['dataset']['repo']}@{result['dataset']['revision']}`", "",
             "| Rank | Arm | Accuracy | Gap closed | Median / p95 | Cost | N |",
             "|---:|---|---:|---:|---:|---:|---:|"]
    for rank, row in enumerate(rows, 1):
        gap = f"{row['gap_closed']:.1%}" if row["gap_closed"] is not None else "—"
        latency = (f"{row['median_seconds']:.1f}s / {row['p95_seconds']:.1f}s"
                   if row["median_seconds"] is not None else "—")
        cost = (f"${row['vendor_usd']:.4f}" if row["vendor_usd"] is not None else "—")
        lines.append(f"| {rank} | {row['arm']} | {row['accuracy']:.1%} | {gap} | "
                     f"{latency} | {cost} | {row['n']} |")
    (run_dir / "report.md").write_text("\n".join(lines) + "\n")
    atomic_json(result_path, result)
    return report


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    index = round((len(values) - 1) * quantile)
    return values[index]
