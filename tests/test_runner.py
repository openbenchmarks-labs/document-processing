import json
import re
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


def test_cost_per_1k_correct_counts_vendor_reader_and_judge(tmp_path):
    rows = [{"bucket": "correct"}] * 8 + [{"bucket": "stale"}] * 2
    payload = {"workflow": "redline-parsing", "split": "tagged", "model": "reader",
               "dataset": {"repo": "example/data", "revision": "abc"},
               "arms": [{"arm": "vendor", "vendor": "Example", "rows": rows,
                         "cost": {"vendor_usd": 1.0, "reader_usd": 0.5, "judge_usd": 0.5,
                                  "llm_usd": 1.0, "total_usd": 2.0}},
                        {"arm": "oracle", "vendor": "reference", "rows": rows,
                         "cost": {"total_usd": 1.0}}]}
    (tmp_path / "result.json").write_text(json.dumps(payload))
    ranking = {row["arm"]: row for row in runner.derive(tmp_path)["ranking"]}
    assert ranking["vendor"]["cost_per_1k_correct"] == 250.0
    assert ranking["oracle"]["cost_per_1k_correct"] is None


class FakeModels:
    """Answers reader calls with 'No.' and judges every answer correct, echoing ids."""

    def __init__(self, judge_reply=None):
        self.reader_calls = 0
        self.judge_calls = 0
        self.judge_reply = judge_reply

    def create(self, **kwargs):
        user = kwargs["input"][-1]["content"]
        if isinstance(user, str) and "Answers to bucket" in user:
            self.judge_calls += 1
            ids = re.findall(r'"id": "([0-9a-f]+)"', user)
            text = (self.judge_reply if self.judge_reply is not None else json.dumps(
                {"verdicts": [{"id": i, "bucket": "correct", "why": "agrees"} for i in ids]}))
            return SimpleNamespace(output_text=text, usage=None, model="judge")
        self.reader_calls += 1
        return SimpleNamespace(output_text="No.", usage=None, model="reader")


def fixture(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"fixture")
    view = tmp_path / "doc.oracle.md"
    view.write_text("The operative answer is No.")
    documents = {"doc": dataset.Document("doc", pdf, {"oracle": view})}
    cases = [dataset.Case("q1", "Is it operative?", "fixture", ["doc"],
                          "No.", "", {"correct": ["No"], "stale": ["Yes"], "fused": []})]
    return cases, documents


def test_mocked_workflow_writes_reusable_artifacts(tmp_path):
    cases, documents = fixture(tmp_path)
    models = FakeModels()
    client = SimpleNamespace(responses=models)
    first = runner.run_arm("oracle", cases, documents, client, "reader", tmp_path / "run",
                           "tagged", judge_model="judge")
    second = runner.run_arm("oracle", cases, documents, client, "reader", tmp_path / "run",
                            "tagged", judge_model="judge")
    assert first["score"]["accuracy"] == 1
    assert first["rows"][0]["token_bucket"] == "correct"
    assert second["rows"][0]["reused"] is True
    assert second["rows"][0]["verdict_reused"] is True
    assert models.reader_calls == 1
    assert models.judge_calls == 1


def test_repeats_and_asks_give_replicates_and_judge_identical_answers_once(tmp_path):
    cases, documents = fixture(tmp_path)
    models = FakeModels()
    client = SimpleNamespace(responses=models)
    result = runner.run_arm("oracle", cases, documents, client, "reader", tmp_path / "run",
                            "tagged", judge_model="judge", repeats=3, asks=3)
    assert len(result["rows"]) == 9
    assert {(row["repeat"], row["ask"]) for row in result["rows"]} == {
        (r, a) for r in (1, 2, 3) for a in (1, 2, 3)}
    assert models.reader_calls == 9
    # Nine identical answers to one question are one verdict, in one call.
    assert models.judge_calls == 1
    assert result["score"]["accuracy_sd"] == 0.0
    assert set(result["cost"]) == {"vendor_usd", "reader_usd", "judge_usd", "llm_usd",
                                   "total_usd"}


def test_unusable_judge_reply_leaves_answer_unscored(tmp_path):
    cases, documents = fixture(tmp_path)
    client = SimpleNamespace(responses=FakeModels(judge_reply="not json"))
    result = runner.run_arm("oracle", cases, documents, client, "reader", tmp_path / "run",
                            "tagged", judge_model="judge")
    assert result["rows"][0]["bucket"] == "unscored"
    assert result["score"]["unscored"] == 1
    assert result["score"]["n"] == 0
