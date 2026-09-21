from openbenchmarks_document_processing.workflows.redline_parsing.evaluation import classify, score


def test_whole_token_matching_avoids_numeric_substrings():
    match = {"correct": ["5"], "stale": ["1.5%"], "fused": []}
    assert classify("The rate is 1.5%.", match) == "stale"


def test_multiple_reference_hits_are_sent_to_judge():
    match = {"correct": ["No"], "stale": ["Yes"], "fused": []}
    assert classify("No, not yes.", match) == "ambiguous"


def test_score_buckets():
    result = score([{"bucket": "correct"}, {"bucket": "correct"}, {"bucket": "stale"}])
    assert result["accuracy"] == 2 / 3
    assert result["stale_rate"] == 1 / 3
