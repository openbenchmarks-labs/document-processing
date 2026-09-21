from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATASET_REPO, DATASET_REVISION, EXPECTED_CASES


@dataclass(frozen=True)
class Document:
    document_id: str
    pdf: Path
    views: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    task_type: str
    documents: list[str]
    expected_answer: str
    expected_detail: str
    match: dict[str, list[str]]


def fetch(root: Path, *, force: bool = False) -> Path:
    """Materialize the exact public dataset revision without transforming it."""
    destination = root / "dataset"
    if destination.exists() and force:
        shutil.rmtree(destination)
    if not destination.exists():
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=DATASET_REPO,
            repo_type="dataset",
            revision=DATASET_REVISION,
            local_dir=destination,
            allow_patterns=["data/eval.jsonl", "documents/*.pdf",
                            "documents_scanned/*.pdf", "views/*.md", "README.md"],
        )
    validate(destination)
    return destination


def load(root: Path, split: str) -> tuple[list[Case], dict[str, Document]]:
    validate(root)
    rows = [json.loads(line) for line in (root / "data/eval.jsonl").read_text().splitlines()
            if line.strip()]
    documents: dict[str, Document] = {}
    cases: list[Case] = []
    pdf_key = "pdf_scanned" if split == "scanned" else "pdf"
    for row in rows:
        for document_id, rel in zip(row["documents"], row[pdf_key], strict=True):
            views = {
                kind: root / "views" / f"{document_id}.{kind}.md"
                for kind in ("oracle", "blind")
                if (root / "views" / f"{document_id}.{kind}.md").is_file()
            }
            documents[document_id] = Document(document_id, root / rel, views)
        cases.append(Case(
            id=row["id"], question=row["question"], task_type=row.get("task_type", ""),
            documents=list(row["documents"]), expected_answer=row["answer"],
            expected_detail=row.get("answer_detail", ""),
            match={"correct": row.get("match_correct") or [],
                   "stale": row.get("match_stale") or [],
                   "fused": row.get("match_fused") or []},
        ))
    return cases, documents


def validate(root: Path) -> None:
    eval_path = root / "data/eval.jsonl"
    if not eval_path.is_file():
        raise SystemExit(f"missing {eval_path}; run init first")
    rows = [json.loads(line) for line in eval_path.read_text().splitlines() if line.strip()]
    if len(rows) != EXPECTED_CASES:
        raise SystemExit(f"expected {EXPECTED_CASES} cases at pinned revision; found {len(rows)}")
    required = {"id", "question", "answer", "documents", "pdf", "pdf_scanned"}
    for number, row in enumerate(rows, 1):
        missing = required - row.keys()
        if missing:
            raise SystemExit(f"eval row {number} missing: {', '.join(sorted(missing))}")
        for key in ("pdf", "pdf_scanned"):
            for rel in row[key]:
                if not (root / rel).is_file():
                    raise SystemExit(f"missing dataset asset: {rel}")


def view_for(case: Case, documents: dict[str, Document], rendered: dict[str, str]) -> str:
    if len(case.documents) == 1:
        return rendered[case.documents[0]]
    return "\n\n".join(
        f"===== DRAFT {document_id} =====\n\n{rendered[document_id]}"
        for document_id in case.documents
    )
