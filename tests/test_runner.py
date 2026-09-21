import json
from types import SimpleNamespace

from openbenchmarks_document_processing.workflows.redline_parsing import dataset, runner


def test_offline_derivation_recomputes_and_sorts(tmp_path):
    payload = {
        "workflow": "redline-parsing", "split": "tagged", "model": "reader",
        "dataset": {"repo": "example/data", "revision": "abc"},
        "arms": [
            {"arm": "low", "rows": [{"bucket": "stale"}], "cost": {}},
            {"arm": "high", "rows": [{"bucket": "correct"}], "cost": {}},
        ],
    }
    (tmp_path / "result.json").write_text(json.dumps(payload))
    report = runner.derive(tmp_path)
    assert [row["arm"] for row in report["ranking"]] == ["high", "low"]
    assert (tmp_path / "report.md").is_file()


def test_derivation_calculates_gap_closed_and_latency(tmp_path):
    def arm(name, correct, seconds):
        return {"arm": name, "rows": ([{"bucket": "correct"}] * correct
                                       + [{"bucket": "stale"}] * (10 - correct)),
                "documents": [{"seconds": value} for value in seconds], "cost": {}}

    payload = {"workflow": "redline-parsing", "split": "tagged", "model": "reader",
               "dataset": {"repo": "example/data", "revision": "abc"},
               "arms": [arm("blind", 2, [1, 3]), arm("oracle", 10, [2, 4]),
                        arm("vendor", 6, [10, 20, 30])]}
    (tmp_path / "result.json").write_text(json.dumps(payload))
    report = runner.derive(tmp_path)
    vendor = next(row for row in report["ranking"] if row["arm"] == "vendor")
    assert vendor["gap_closed"] == 0.5
    assert vendor["median_seconds"] == 20


def test_mocked_workflow_writes_reusable_artifacts(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"fixture")
    view = tmp_path / "doc.oracle.md"
    view.write_text("The operative answer is No.")
    documents = {"doc": dataset.Document("doc", pdf, {"oracle": view})}
    cases = [dataset.Case("q1", "Is it operative?", "fixture", ["doc"],
                          "No.", "", {"correct": ["No"], "stale": ["Yes"], "fused": []})]

    class Responses:
        calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            return SimpleNamespace(output_text="No.", usage=None, model="reader")

    responses = Responses()
    client = SimpleNamespace(responses=responses)
    first = runner.run_arm("oracle", cases, documents, client, "reader", tmp_path / "run", "tagged")
    second = runner.run_arm("oracle", cases, documents, client, "reader", tmp_path / "run", "tagged")
    assert first["score"]["accuracy"] == 1
    assert second["rows"][0]["reused"] is True
    assert responses.calls == 1
