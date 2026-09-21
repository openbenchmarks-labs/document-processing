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
