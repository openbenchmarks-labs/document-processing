from __future__ import annotations

import json
import random
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import evaluation, pricing, providers
from .dataset import Case, Document, view_for
from .environment import usage_of
from .storage import atomic_json, cache_key, load_cached

SYSTEM = (
    "You answer questions about a contract using only the document text you are "
    "given. The text may contain edit markup. Answer in one short sentence."
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


def slot(repeat: int, ask_number: int) -> str:
    """The answer-cache suffix for one (parse repeat, ask). The first ask of the
    first parse has none, so a single-shot run's answers are that slot."""
    return "" if repeat <= 1 and ask_number <= 1 else f".r{repeat}a{ask_number}"


def run_arm(arm: str, cases: list[Case], documents: dict[str, Document], client,
            model: str, run_dir: Path, split: str, *, judge_model: str,
            repeats: int = 1, asks: int = 1, concurrency: int = 8,
            batch: int = evaluation.BATCH_SIZE) -> dict:
    """Parse, ask and judge one arm.

    Each contract is parsed `repeats` times and each question is asked `asks`
    times against every parse, so one question yields repeats x asks answers.
    The reader and the judge are separate models: every answer is bucketed by
    `judge_model`, in batches that share one question.
    """
    parse_cache = run_dir / "parsed" / split
    answers_dir = run_dir / "answers" / split / arm
    rendered: dict[tuple[str, int], str] = {}
    parse_meta: list[dict] = []
    wanted = sorted({doc for case in cases for doc in case.documents})
    for index, document_id in enumerate(wanted, 1):
        for repeat in range(1, repeats + 1):
            markdown, meta = providers.render(documents[document_id], arm, parse_cache,
                                              repeat=repeat)
            rendered[(document_id, repeat)] = markdown
            cost = pricing.cost_of_parse(arm, meta)
            parse_meta.append({"document_id": document_id, "repeat": repeat, "cost": cost,
                               **meta})
        print(f"[{arm}] parsed {index}/{len(wanted)} {document_id}", flush=True)

    # -- reader ---------------------------------------------------------------
    jobs = [(index, case, repeat, ask_number)
            for index, case in enumerate(cases)
            for repeat in range(1, repeats + 1)
            for ask_number in range(1, asks + 1)]
    lock = threading.Lock()
    done = [0]

    def answer(job: tuple[int, Case, int, int]) -> tuple[int, int, int, dict]:
        index, case, repeat, ask_number = job
        markdown = view_for(case, documents,
                            {doc: rendered[(doc, repeat)] for doc in case.documents})
        key = cache_key(model, SYSTEM, PROMPT, case.question, markdown,
                        str(repeat), str(ask_number))
        path = answers_dir / f"{case.id}{slot(repeat, ask_number)}.json"
        cached = load_cached(path, key)
        if cached:
            row = {**cached["row"], "reused": True}
        else:
            prefix = f"{arm}:r{repeat}:{'+'.join(sorted(case.documents))}"
            try:
                text, hop = ask(client, model, markdown, case.question, prefix)
                error = None
            except Exception as exc:  # noqa: BLE001 - classified immediately below
                # A dead key or an empty account fails every answer the same way;
                # stop the run instead of saving an arm of unscored rows.
                if providers.classify(exc)[1] == "fatal":
                    raise providers.FatalVendorError(f"reader {model}: {exc}") from exc
                text, hop, error = "", {}, f"{type(exc).__name__}: {str(exc)[:300]}"
            row = {"id": case.id, "task_type": case.task_type, "documents": case.documents,
                   "repeat": repeat, "ask": ask_number, "answer": text,
                   "token_bucket": evaluation.classify(text, case.match) if text else None,
                   "usage": hop.get("response", {}).get("usage") or {},
                   "llm_seconds": hop.get("response", {}).get("seconds"),
                   "reused": False}
            if error:
                row["error"] = error
            elif text:
                # An empty answer is not cached: it would stay unscored on every
                # resume instead of being asked again.
                atomic_json(path, {"key": key, "answer": text, "ask": hop, "row": row})
        with lock:
            done[0] += 1
            if done[0] % 25 == 0 or done[0] == len(jobs):
                print(f"[{arm}] answered {done[0]}/{len(jobs)}", flush=True)
                atomic_json(run_dir / "progress.json", {
                    "arm": arm, "status": "answering", "cases_complete": done[0],
                    "cases_total": len(jobs)})
        return index, repeat, ask_number, row

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        answered = list(pool.map(answer, jobs))
    rows = [row for *_, row in sorted(answered, key=lambda item: item[:3])]

    # -- judge ----------------------------------------------------------------
    judge = judge_rows(arm, rows, cases, client, judge_model, run_dir, split,
                       batch=batch, concurrency=concurrency)

    vendor_usd = sum((item["cost"].get("usd") or 0) for item in parse_meta)
    reader_usd = sum((pricing.cost_of_llm(model, row.get("usage")).get("usd") or 0)
                     for row in rows)
    llm_usd = reader_usd + judge["usd"]
    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_type[row["task_type"]].append(row)
    return {"arm": arm, **providers.identity(arm), "repeats": repeats, "asks": asks,
            "score": evaluation.score(rows),
            "by_task_type": {name: evaluation.score(items)
                             for name, items in sorted(by_type.items())},
            "cost": {"vendor_usd": round(vendor_usd, 6), "reader_usd": round(reader_usd, 6),
                     "judge_usd": round(judge["usd"], 6), "llm_usd": round(llm_usd, 6),
                     "total_usd": round(vendor_usd + llm_usd, 6)},
            "judge": judge, "documents": parse_meta, "rows": rows}


def judge_rows(arm: str, rows: list[dict], cases: list[Case], client, model: str,
               run_dir: Path, split: str, *, batch: int, concurrency: int) -> dict:
    """Bucket every answer in place. Identical answers to one question are judged
    once, verdicts are cached per (judge model, references, answer), and an answer
    the judge cannot bucket after a retry is left `unscored`, never counted wrong."""
    by_id = {case.id: case for case in cases}
    verdict_dir = run_dir / "answers" / split / f"_judge-{model}"
    pending: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    # A verdict reused on a resumed run was paid for when it was first judged;
    # its share is carried in the cache so the arm's judge cost does not depend
    # on how many times the run was resumed. Counted once per distinct answer.
    reused_usd = 0.0
    reused = 0
    reused_keys: set[str] = set()
    for row in rows:
        if row.get("error") or not row.get("answer"):
            row.update({"bucket": "unscored", "judged": False})
            continue
        refs = evaluation.references(by_id[row["id"]])
        key = cache_key(model, evaluation.BATCH_VERSION, evaluation.SYSTEM, evaluation.PROMPT,
                        refs["question"], refs["correct"], refs["stale"], refs["fused"],
                        evaluation.norm_ws(row["answer"]))
        hit = load_cached(verdict_dir / f"{row['id']}.{key[:16]}.judge.json", key)
        if hit:
            row.update({"bucket": hit["bucket"], "judge_why": hit["why"], "judged": True,
                        "judge_model": model, "verdict_reused": True})
            reused += 1
            if key not in reused_keys:
                reused_keys.add(key)
                reused_usd += float(hit.get("usd") or 0.0)
            continue
        pending[row["id"]][key].append(row)

    batches: list[tuple[str, list[str]]] = []
    for case_id, answers in pending.items():
        keys = sorted(answers)
        # Shuffled per question with a fixed seed: the order a judge sees answers
        # in should not follow repeat order, and a rerun should see the same order.
        random.Random(case_id).shuffle(keys)
        for start in range(0, len(keys), max(1, batch)):
            batches.append((case_id, keys[start:start + batch]))

    lock = threading.Lock()
    calls: list[dict] = []

    def apply(case_id: str, key: str, bucket: str, why: str, usd: float) -> None:
        for row in pending[case_id][key]:
            row.update({"bucket": bucket, "judge_why": why, "judged": bucket != "unscored",
                        "judge_model": model, "verdict_reused": False})
        if bucket in evaluation.SCORED:
            atomic_json(verdict_dir / f"{case_id}.{key[:16]}.judge.json",
                        {"key": key, "bucket": bucket, "why": why, "usd": usd})

    def one_batch(item: tuple[str, list[str]]) -> None:
        case_id, keys = item
        refs = evaluation.references(by_id[case_id])
        todo = [(key[:16], key) for key in keys]
        # One try at full size, then the stragglers once more in a smaller call.
        for attempt in (1, 2):
            try:
                verdicts, missing, hop = evaluation.judge_batch(
                    client, model, refs,
                    [(short, pending[case_id][key][0]["answer"]) for short, key in todo])
                error = None
            except Exception as exc:  # noqa: BLE001 - classified immediately below
                if providers.classify(exc)[1] == "fatal":
                    raise providers.FatalVendorError(f"judge {model}: {exc}") from exc
                verdicts, missing, hop = {}, [short for short, _ in todo], {}
                error = f"{type(exc).__name__}: {str(exc)[:200]}"
            usage = hop.get("response", {}).get("usage") or {}
            usd = pricing.cost_of_llm(model, usage).get("usd") or 0.0
            share = usd / max(1, len(todo))
            with lock:
                calls.append({"case_id": case_id, "attempt": attempt, "items": len(todo),
                              "usd": usd, "error": error})
                for short, key in todo:
                    if short in verdicts:
                        bucket, why = verdicts[short]
                        apply(case_id, key, bucket, why, share)
            if not missing:
                return
            todo = [(short, key) for short, key in todo if short in set(missing)]
        with lock:
            for _, key in todo:
                apply(case_id, key, "unscored", "judge returned no usable verdict", 0.0)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(one_batch, batches))
    if batches:
        print(f"[{arm}] judged {sum(len(k) for _, k in batches)} distinct answers in "
              f"{len(calls)} call(s), {reused} verdicts reused", flush=True)

    return {"model": model, "version": evaluation.BATCH_VERSION, "batch": batch,
            "calls": len(calls), "failed_calls": sum(1 for c in calls if c["error"]),
            "verdicts_reused": reused,
            "usd": round(sum(c["usd"] for c in calls) + reused_usd, 6)}


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
        # The board's cost columns are per pass: one parse of the corpus and one
        # answer per question, averaged over the replicates, so a 3x3 run and a
        # single-shot run price the same thing.
        cost = arm.get("cost") or {}
        repeats, asks = arm.get("repeats") or 1, arm.get("asks") or 1
        all_rows = arm.get("rows") or []
        questions = len(all_rows) / (repeats * asks) if all_rows else 0
        correct = score["accuracy"] * questions
        pages = sum((doc.get("cost") or {}).get("pages") or doc.get("n_pages") or 0
                    for doc in arm.get("documents", []) if (doc.get("repeat") or 1) == 1)
        vendor = cost.get("vendor_usd")
        is_reference = arm.get("vendor") == "reference"
        parse_pass = vendor / repeats if vendor is not None and not is_reference else None
        tokens = sum(((row.get("usage") or {}).get("input_tokens") or 0)
                     + ((row.get("usage") or {}).get("output_tokens") or 0) for row in all_rows)
        tokens_pass = tokens / (repeats * asks) if tokens else None
        per_1k_pages = round(parse_pass / pages * 1000, 4) if parse_pass is not None and pages else None
        per_1k = round(parse_pass / correct * 1000, 4) if parse_pass is not None and correct else None
        tokens_1k = round(tokens_pass / correct * 1000) if tokens_pass and correct else None
        rows.append({"arm": arm["arm"], "accuracy": score["accuracy"],
                     "accuracy_sd": score.get("accuracy_sd"),
                     "stale_rate": score["stale_rate"], "fused_rate": score["fused_rate"],
                     "n": score["n"], "unscored": score["unscored"],
                     "gap_closed": gap, "median_seconds": median, "p95_seconds": p95,
                     "vendor_usd": cost.get("vendor_usd"), "total_usd": cost.get("total_usd"),
                     "parser_usd_per_1k_pages": per_1k_pages,
                     "parser_usd_per_1k_correct": per_1k,
                     "tokens_per_1k_correct": tokens_1k})
    rows.sort(key=lambda item: (-item["accuracy"], item["arm"]))
    report = {"workflow": result["workflow"], "dataset": result["dataset"],
              "split": result["split"], "model": result["model"],
              "judge_model": result.get("judge_model"),
              "repeats": result.get("repeats"), "asks": result.get("asks"),
              "ranking": rows}
    atomic_json(run_dir / "report.json", report)
    lines = ["# Redline parsing benchmark", "",
             f"Dataset: `{result['dataset']['repo']}@{result['dataset']['revision']}`",
             f"Reader: `{result['model']}` · judge: `{result.get('judge_model') or 'n/a'}` · "
             f"{result.get('repeats') or 1} parse(s) x {result.get('asks') or 1} ask(s)", "",
             "| Rank | Arm | Accuracy | Gap closed | Median parse time | Parser $ / 1k pages "
             "| Parser $ / 1k correct | Total tokens / 1k correct | Stale | Fused | Unscored | N |",
             "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rank, row in enumerate(rows, 1):
        accuracy = f"{row['accuracy']:.1%}"
        if row["accuracy_sd"] is not None:
            accuracy += f" ± {row['accuracy_sd']:.1%}"
        gap = f"{row['gap_closed']:.0%}" if row["gap_closed"] is not None else "n/a"
        latency = (f"{row['median_seconds']:.0f}s (p95 {row['p95_seconds']:.0f}s)"
                   if row["median_seconds"] is not None else "n/a")
        usd = lambda v: f"${v:.2f}" if v is not None else "n/a"  # noqa: E731
        tokens = row["tokens_per_1k_correct"]
        tokens_text = ("n/a" if tokens is None else
                       f"{tokens / 1e6:.1f}M" if tokens >= 1e6 else f"{tokens / 1e3:.0f}K")
        lines.append(f"| {rank} | {row['arm']} | {accuracy} | {gap} | {latency} | "
                     f"{usd(row['parser_usd_per_1k_pages'])} | {usd(row['parser_usd_per_1k_correct'])} | "
                     f"{tokens_text} | {row['stale_rate']:.1%} | {row['fused_rate']:.1%} | "
                     f"{row['unscored']} | {row['n']} |")
    (run_dir / "report.md").write_text("\n".join(lines) + "\n")
    atomic_json(result_path, result)
    return report


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    index = round((len(values) - 1) * quantile)
    return values[index]
