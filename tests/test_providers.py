from dataclasses import dataclass
from pathlib import Path

from openbenchmarks_document_processing.workflows.redline_parsing import providers


@dataclass
class Doc:
    document_id: str
    pdf: Path
    views: dict


def test_parse_cache_invalidates_on_pdf_and_settings(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"one")
    doc = Doc("doc", pdf, {})
    calls = []

    def fake(_pdf):
        calls.append(_pdf.read_bytes())
        return "markdown", {"n_pages": 1}

    monkeypatch.setitem(providers.VENDORS, "fixture", fake)
    monkeypatch.setitem(providers.SETTINGS, "fixture", {"mode": "a"})
    providers.render(doc, "fixture", tmp_path / "cache")
    providers.render(doc, "fixture", tmp_path / "cache")
    assert len(calls) == 1

    pdf.write_bytes(b"two")
    providers.render(doc, "fixture", tmp_path / "cache")
    assert len(calls) == 2

    providers.SETTINGS["fixture"] = {"mode": "b"}
    providers.render(doc, "fixture", tmp_path / "cache")
    assert len(calls) == 3


def test_provider_exchange_redacts_secrets():
    assert providers._redact({"Authorization": "secret", "x": "ok"}) == {
        "Authorization": "<redacted>", "x": "ok"
    }
