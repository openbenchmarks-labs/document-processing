from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from .workflows.registry import WORKFLOWS
from .workflows.redline_parsing import dataset, providers, runner
from .workflows.redline_parsing.config import (
    DATASET_REPO, DATASET_REVISION, EXPECTED_CASES, SMOKE_CASES, UPSTREAM_REPO,
    UPSTREAM_REVISION, WORKFLOW,
)
from .workflows.redline_parsing.environment import DEFAULT_MODEL, make_llm_client
from .workflows.redline_parsing.storage import atomic_json, utc_stamp

PUBLIC_ARMS = ("oracle", "blind", *sorted(providers.VENDORS))


def _workflow(value: str) -> str:
    if value not in WORKFLOWS:
        raise argparse.ArgumentTypeError(f"unknown workflow {value!r}")
    return value


def _arms(value: str) -> list[str]:
    chosen = list(PUBLIC_ARMS) if value == "all" else [part.strip() for part in value.split(",")]
    unknown = sorted(set(chosen) - set(PUBLIC_ARMS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown public arms: {', '.join(unknown)}")
    if not chosen:
        raise argparse.ArgumentTypeError("choose at least one arm")
    return chosen


def _common_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workflow", default=WORKFLOW, type=_workflow)
    parser.add_argument("--split", choices=("tagged", "scanned"), default="tagged")
    parser.add_argument("--arms", required=True, type=_arms,
                        help="Comma-separated public arms, or all.")
    parser.add_argument("--data-dir", type=Path, default=Path(".openbench/redline-parsing"))
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--model", default=os.environ.get("DOC_PROCESSING_MODEL", DEFAULT_MODEL))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openbench-document-processing")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-workflows", help="List installed benchmark workflows.")

    init = sub.add_parser("init", help="Download and validate the pinned public dataset.")
    init.add_argument("--workflow", default=WORKFLOW, type=_workflow)
    init.add_argument("--split", choices=("tagged", "scanned"), default="tagged")
    init.add_argument("--data-dir", type=Path, default=Path(".openbench/redline-parsing"))
    init.add_argument("--force", action="store_true")

    smoke = sub.add_parser("smoke", help="Run the deterministic 12-question subset.")
    _common_run(smoke)

    run = sub.add_parser("run", help="Run all 95 public questions.")
    _common_run(run)
    run.add_argument("--full", action="store_true", required=True)
    run.add_argument("--approve-full", action="store_true",
                     help="Acknowledge that selected vendor/model calls can incur charges.")
    run.add_argument("--approval-id", help="Audit identifier recorded in the run manifest.")

    watch = sub.add_parser("watch", help="Show local run progress.")
    watch.add_argument("--workflow", default=WORKFLOW, type=_workflow)
    watch.add_argument("--run-dir", type=Path, required=True)

    derive = sub.add_parser("derive-full-run", help="Recompute reports from local artifacts only.")
    derive.add_argument("--workflow", default=WORKFLOW, type=_workflow)
    derive.add_argument("--run-dir", type=Path, required=True)
    return parser


def _manifest(args, mode: str, selected: list) -> dict:
    return {
        "schema_version": 1, "workflow": WORKFLOW, "mode": mode, "split": args.split,
        "arms": args.arms, "model": args.model, "case_ids": [case.id for case in selected],
        "dataset": {"repo": DATASET_REPO, "revision": DATASET_REVISION,
                    "upstream_repo": UPSTREAM_REPO, "upstream_revision": UPSTREAM_REVISION},
        "approval_id": getattr(args, "approval_id", None),
    }


def _execute(args, mode: str) -> int:
    if mode == "full" and (not args.approve_full or not args.approval_id):
        raise SystemExit("full runs require --approve-full and a non-empty --approval-id")
    dataset_root = dataset.fetch(args.data_dir)
    cases, documents = dataset.load(dataset_root, args.split)
    if mode == "smoke":
        cases = sorted(cases, key=lambda case: hashlib.sha256(case.id.encode()).digest())[:SMOKE_CASES]
    run_dir = args.run_dir or Path("runs") / f"{utc_stamp()}-{args.split}-{mode}"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(args, mode, cases)
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        immutable = ("workflow", "mode", "split", "arms", "model", "case_ids", "dataset",
                     "approval_id")
        if any(old.get(key) != manifest.get(key) for key in immutable):
            raise SystemExit("run directory belongs to a different immutable configuration")
        manifest = old
    else:
        atomic_json(manifest_path, manifest)

    result_path = run_dir / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {
        "workflow": WORKFLOW, "split": args.split, "model": args.model,
        "dataset": manifest["dataset"], "arms": [],
    }
    done = {entry["arm"] for entry in result["arms"]}
    client = make_llm_client()
    for arm in args.arms:
        if arm in done:
            print(f"[{arm}] already complete", flush=True)
            continue
        result["arms"].append(runner.run_arm(
            arm, cases, documents, client, args.model, run_dir, args.split))
        atomic_json(result_path, result)
        runner.derive(run_dir)
        atomic_json(run_dir / "progress.json", {"arm": arm, "status": "complete",
                                                 "cases_complete": len(cases),
                                                 "cases_total": len(cases)})
    print(run_dir.resolve())
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list-workflows":
        for name, item in WORKFLOWS.items():
            print(f"{name}\t{item['description']}")
        return 0
    if args.command == "init":
        root = dataset.fetch(args.data_dir, force=args.force)
        atomic_json(args.data_dir / "dataset-lock.json", {
            "workflow": WORKFLOW, "split_requested": args.split,
            "repo": DATASET_REPO, "revision": DATASET_REVISION,
            "cases": EXPECTED_CASES,
        })
        print(root.resolve())
        return 0
    if args.command == "smoke":
        return _execute(args, "smoke")
    if args.command == "run":
        return _execute(args, "full")
    if args.command == "watch":
        result = args.run_dir / "result.json"
        manifest = args.run_dir / "manifest.json"
        if not manifest.is_file():
            raise SystemExit(f"missing {manifest}")
        state = json.loads(result.read_text()) if result.is_file() else {"arms": []}
        wanted = json.loads(manifest.read_text())["arms"]
        complete = [arm["arm"] for arm in state.get("arms", [])]
        print(f"{len(complete)}/{len(wanted)} arms complete: {', '.join(complete) or 'none'}")
        progress = args.run_dir / "progress.json"
        if progress.is_file():
            item = json.loads(progress.read_text())
            label = "active" if item.get("status") != "complete" else "last completed"
            print(f"{label} {item['arm']}: {item['cases_complete']}/{item['cases_total']} cases")
        return 0
    if args.command == "derive-full-run":
        report = runner.derive(args.run_dir)
        print(json.dumps(report["ranking"], indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
