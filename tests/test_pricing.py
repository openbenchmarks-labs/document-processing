from openbenchmarks_document_processing.workflows.redline_parsing.pricing import (
    cost_of_llm, cost_of_parse,
)


def test_parser_cost_prefers_vendor_reported_cost():
    result = cost_of_parse("datalab", {"n_pages": 10,
                                       "cost_cents": {"final_cost_cents": 7}})
    assert result["usd"] == 0.07
    assert result["basis"] == "vendor cost"


def test_llm_cost_accounts_for_cached_tokens():
    result = cost_of_llm("gpt-5.6-sol", {
        "input_tokens": 1000, "output_tokens": 100,
        "input_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 0},
    })
    assert result["priced"] is True
    assert result["tokens_cached"] == 800


def test_gpt6_reader_and_judge_are_priced():
    for model in ("gpt-6-luna", "gpt-6-sol"):
        result = cost_of_llm(model, {"input_tokens": 100_000, "output_tokens": 0})
        assert result["priced"] is True
    luna = cost_of_llm("gpt-6-luna", {"input_tokens": 100_000, "output_tokens": 0})
    assert luna["usd"] == 0.01


def test_unstructured_is_priced_from_the_rate_card():
    result = cost_of_parse("unstructured", {"n_pages": 10})
    assert result["usd"] == 0.15
    assert result["basis"] == "rate card"
