from openbenchmarks_document_processing.workflows.redline_parsing.evaluation import (
    classify, parse_verdicts, score,
)


def test_whole_token_matching_avoids_numeric_substrings():
    match = {"correct": ["5"], "stale": ["1.5%"], "fused": []}
    assert classify("The rate is 1.5%.", match) == "stale"


def test_multiple_reference_hits_are_ambiguous():
    match = {"correct": ["No"], "stale": ["Yes"], "fused": []}
    assert classify("No, not yes.", match) == "ambiguous"


def test_score_buckets():
    result = score([{"bucket": "correct"}, {"bucket": "correct"}, {"bucket": "stale"}])
    assert result["accuracy"] == 2 / 3
    assert result["stale_rate"] == 1 / 3


def test_unscored_rows_leave_the_denominator():
    result = score([{"bucket": "correct"}, {"bucket": "unscored"}])
    assert result["accuracy"] == 1
    assert result["unscored"] == 1
    assert result["n"] == 1


def test_replicate_sd_across_repeat_and_ask():
    rows = [{"bucket": "correct", "repeat": 1, "ask": 1},
            {"bucket": "stale", "repeat": 2, "ask": 1}]
    result = score(rows)
    assert result["replicates"] == {"r1a1": 1.0, "r2a1": 0.0}
    assert round(result["accuracy_sd"], 4) == 0.7071


def test_parse_verdicts_ignores_unknown_ids_and_disagreeing_duplicates():
    text = ('{"verdicts": [{"id": "a", "bucket": "correct", "why": "x"},'
            ' {"id": "b", "bucket": "stale"}, {"id": "b", "bucket": "correct"},'
            ' {"id": "z", "bucket": "correct"}, {"id": "c", "bucket": "nonsense"}]}')
    verdicts, missing = parse_verdicts(text, ["a", "b", "c"])
    assert verdicts == {"a": ("correct", "x")}
    assert missing == ["b", "c"]


def test_unreadable_judge_reply_is_no_verdicts():
    assert parse_verdicts("no json here", ["a"]) == ({}, ["a"])


def test_braces_before_the_verdict_object_do_not_drop_the_batch():
    text = ('Considered the set {a, b}.\n'
            '{"verdicts": [{"id": "a", "bucket": "correct", "why": "matches"}]}')
    verdicts, missing = parse_verdicts(text, ["a"])
    assert verdicts == {"a": ("correct", "matches")}
    assert missing == []
