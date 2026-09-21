import json

from openbenchmarks_document_processing.workflows.redline_parsing import dataset
from openbenchmarks_document_processing.workflows.redline_parsing.config import EXPECTED_CASES


def public_fixture(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents_scanned").mkdir()
    (tmp_path / "views").mkdir()
    (tmp_path / "documents/doc.pdf").write_bytes(b"%PDF fixture")
    (tmp_path / "documents_scanned/doc.pdf").write_bytes(b"%PDF scanned fixture")
    (tmp_path / "views/doc.oracle.md").write_text("kept ~~deleted~~")
    (tmp_path / "views/doc.blind.md").write_text("kept deleted")
    rows = []
    for number in range(EXPECTED_CASES):
        rows.append(json.dumps({
            "id": f"q-{number:03d}", "question": "Is it kept?", "answer": "No.",
            "documents": ["doc"], "pdf": ["documents/doc.pdf"],
            "pdf_scanned": ["documents_scanned/doc.pdf"], "match_correct": ["No"],
            "match_stale": ["Yes"], "match_fused": [], "task_type": "fixture",
        }))
    (tmp_path / "data/eval.jsonl").write_text("\n".join(rows) + "\n")
    return tmp_path


def test_loads_tagged_and_scanned(tmp_path):
    root = public_fixture(tmp_path)
    cases, tagged = dataset.load(root, "tagged")
    _, scanned = dataset.load(root, "scanned")
    assert len(cases) == EXPECTED_CASES
    assert tagged["doc"].pdf.parent.name == "documents"
    assert scanned["doc"].pdf.parent.name == "documents_scanned"
    assert set(tagged["doc"].views) == {"oracle", "blind"}
