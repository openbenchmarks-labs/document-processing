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


def test_unstructured_key_header_is_redacted():
    assert providers._redact({"unstructured-api-key": "secret", "Prefer": "wait=0"}) == {
        "unstructured-api-key": "<redacted>", "Prefer": "wait=0"
    }


def test_repeat_parses_use_own_slot_and_bypass_vendor_cache(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"one")
    doc = Doc("doc", pdf, {})
    calls = []

    def fake(_pdf, *, fresh=False):
        calls.append(fresh)
        return f"markdown {len(calls)}", {"n_pages": 1}

    monkeypatch.setitem(providers.VENDORS, "fixture", fake)
    monkeypatch.setitem(providers.SETTINGS, "fixture", {"mode": "a"})
    monkeypatch.setattr(providers, "VENDOR_CACHE_BYPASS", frozenset({"fixture"}))
    first, meta1 = providers.render(doc, "fixture", tmp_path / "cache", repeat=1)
    second, meta2 = providers.render(doc, "fixture", tmp_path / "cache", repeat=2)
    again, meta3 = providers.render(doc, "fixture", tmp_path / "cache", repeat=2)
    assert calls == [False, True]
    assert (first, second, again) == ("markdown 1", "markdown 2", "markdown 2")
    assert meta2["vendor_cache_bypassed"] is True and meta3["cached"] is True
    assert (tmp_path / "cache" / "doc.fixture.r2.md").is_file()


def test_dated_builds_are_in_the_fingerprint():
    assert providers.SETTINGS["extend"]["build"] == providers.EXTEND_BUILD
    assert providers.SETTINGS["reducto"]["build"] == providers.REDUCTO_BUILD
    assert "unstructured" in providers.VENDORS
    assert providers.tracked_changes("unstructured") is False
