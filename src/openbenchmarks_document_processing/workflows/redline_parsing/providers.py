"""Render one contract PDF to markdown, once per arm.

Ported from the dataset repo unchanged in every part that touches a vendor: the
endpoints, engines and flags here are the same ones the published numbers were
produced with, and a quiet difference in, say, Pulse's formatting flag would
move a score without moving the parser.

Two kinds of arm share this interface. Vendors are billed API calls against the
PDF. The reference arms are not calls at all -- oracle, blind and accepted ship
inside the snapshot, rendered from the source file the snapshot withholds, and
they exist to bound the scale: oracle is what a perfect strike-preserving parse
would give an agent, blind is what a parser that drops the markup gives it.

Parsing is per document, never per question. Roughly nineteen questions share
one contract, and the cache is keyed on the PDF's sha256, so an unchanged
document is never billed twice.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REFERENCE_ARMS = ("oracle", "blind", "accepted")

LLAMAPARSE_TIER = "agentic"
# Pinned, not `latest`. On 2026-09-10 `latest` began resolving to the freshly
# published agentic build 2026-09-09, which the parse endpoint then rejected as
# an invalid tier/version combination mid-run. A rolling version also means two
# runs of this arm can score different parses, which is the one thing a board
# cannot allow. The board was re-run on the 2026-09-24 build of both tiers.
LLAMAPARSE_VERSION = "2026-09-24"
# The vendor's premium tier, run as its own arm rather than replacing `agentic`:
# the published numbers were produced on agentic, so swapping it out would break
# comparability, while hiding it would leave llamaparse the only vendor not
# measured at its best setting.
LLAMAPARSE_PLUS_TIER = "agentic_plus"
LLAMAPARSE_PLUS_VERSION = "2026-09-24"
REDUCTO_MODEL = "r-1"
# Tracked changes are opt-in on Reducto exactly as they are on Pulse: without
# `change_tracking` in the include list the struck text comes back as ordinary
# prose and the arm measures a flag rather than the parser.
REDUCTO_FORMATTING = {"include": ["change_tracking"]}
# Reducto moved r-1 to a new model on 2026-09-25 behind the same invocation: the
# request is byte-identical, only what answers it changed. The date goes into the
# settings fingerprint (never into the request) so a parse cached before the
# change misses instead of being scored as the new model.
REDUCTO_BUILD = "2026-09-25"
# Highest-accuracy engine. Agentic OCR stays off: these are clean digital PDFs,
# where the vendor's own guidance is that it only adds latency.
EXTEND_ENGINE = "parse_performance"
# Same opt-in as Pulse and Reducto. Extend documents `change_tracking` as
# detecting "insertions, deletions, substitutions indicated by strikethroughs,
# colored text, or underlines", which is the entire signal this bench scores.
EXTEND_ADVANCED = {"formattingDetection": [{"type": "change_tracking"}]}
PULSE_URL = "https://api.runpulse.com/extract"
PULSE_MODEL = "pulse-ultra-2"
# Strikethrough is opt-in on Pulse. Without refine_options.formatting the model
# returns deleted text as ordinary prose, so the benchmark's whole signal turns
# on this flag; tables and text refinement are on too so the arm is the vendor's
# best case rather than a handicapped default.
PULSE_REFINE = {"text": True, "tables": True, "formatting": True}
MISTRAL_URL = "https://api.mistral.ai/v1/ocr"
# The concrete id, not the `mistral-ocr-latest` alias it currently answers to.
# The alias also points at `mistral-ocr-4`, and a board number has to name the
# model that produced it rather than whatever the alias means when you read it.
MISTRAL_MODEL = "mistral-ocr-4-1"
DATALAB_URL = "https://www.datalab.to/api/v1/convert"
# Datalab's purpose-built tracked-changes endpoint. The prose docs describe it as
# a DOCX feature, but its OpenAPI schema accepts PDF, and only the PDF is a fair
# arm here — handing it the .docx would let it read the answer key out of OOXML
# instead of recovering the edit from the page.
DATALAB_TC_URL = "https://www.datalab.to/api/v1/track-changes"
# Highest-accuracy mode; the vendor recommends it for exactly our shape of input
# (complex tables, dense layouts). Conversion is async, so the call polls.
DATALAB_MODE = "accurate"
DATALAB_POLL_SECONDS = 5
DATALAB_MAX_WAIT = 1800

# The frontier arms. These are general models asked to do a parser's job, so the
# only thing that makes them comparable to the vendors above -- or to each other
# -- is that they get exactly the same input and exactly the same instruction.
#
# Same input: the PDF, whole, as bytes. Not page images. ParseBench rasterises
# at 150 DPI and sends one request per page, which is a reasonable choice for a
# board of nothing but VLMs, but here it would quietly hand the frontier arms a
# different question than the vendors get. Every vendor arm receives this file
# and decides for itself how to render it; letting us pick the DPI would make
# our rendering part of the measurement. It is also cheaper on both models.
#
# Same instruction: VLM_PROMPT, below, for every frontier arm.
ASTRA_MODEL = "gpt-6-astra"
FABLE_MODEL = "us.anthropic.claude-fable-5-1"
# Bedrock is the account we already hold Anthropic capacity on -- the same one
# the web-search judge runs through -- so the arm reuses that path rather than
# opening a second billing relationship. Note the `us.` inference profile costs
# 10% over `global.`; we take the premium to keep the region pinned, because the
# account's data-retention mode is set per region and Fable is gated on it.
# Contracts here average 24.5 pages and reach 38, and one call parses the whole
# document. A single page came back as ~1.1-3.7k output tokens depending on how
# much the model chose to think, so the ceiling has to clear ~90k to be safe on
# the long tail; 8192 -- the figure ParseBench uses for its one-page-per-request
# design -- would truncate a typical contract around page three and score the
# arm on a fragment. 100k against Fable's 128k maximum leaves headroom without
# pretending truncation cannot happen: both arms check for it explicitly.
FABLE_MAX_TOKENS = 100_000
# A whole contract in one call takes minutes, not seconds: the 38-page worst
# case ran 373s on the faster of the two frontier arms. The web-search judge's
# Bedrock client is configured read_timeout=180 for short scoring calls and is a
# cached module-level singleton, so this arm builds its own rather than widening
# a timeout the judge relies on. Retries are left to the harness, which knows
# which failures are worth repeating and logs the attempt.
FABLE_READ_TIMEOUT = 1800
_FABLE_CLIENT = None

# One prompt, every frontier arm, and deliberately silent about strikethrough.
#
# The temptation is to write "preserve struck text as ~~like this~~", and on a
# single page that helped one model and hurt another, which is to say it was
# noise. The real argument against it is fairness in the other direction: the
# vendor arms are not told what this benchmark is looking for either. Four of
# them are sent an opt-in flag that means "return tracked changes", and that
# flag is recorded in TRACKED_CHANGES_OPT_IN precisely so a reader can tell a
# parser that found the strike from one that was handed it. A prompt naming
# strikethrough is the frontier equivalent of that flag, and an arm that gets it
# is a different measurement -- so it would need its own slug and its own row,
# not a quiet edit to this string.
#
# What the models are asked for is what a document parser sells: the page, in
# markdown, faithfully. Whether "faithfully" includes the deletions is the thing
# under test.
VLM_PROMPT = (
    "Convert this document to clean, well-structured markdown. "
    "Reproduce the page faithfully, preserving headings, paragraphs, lists, "
    "tables and inline formatting. Output only the document content, with no "
    "commentary, preamble or code fences."
)


def _page_count(pdf: Path) -> int:
    """Pages in the file, for the trace. The frontier arms bill per token, so
    unlike the vendors this is reporting rather than an input to the bill."""
    from pypdf import PdfReader

    return len(PdfReader(str(pdf)).pages)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VendorError(RuntimeError):
    """A vendor call that failed. Costs this arm, not the run."""

    def __init__(self, message: str, *, status: int | None = None, arm: str = ""):
        super().__init__(message)
        self.status = status
        self.arm = arm


class FatalVendorError(VendorError):
    """Out of credit, unauthorised, or otherwise not worth trying again anywhere.

    Separate from VendorError because the response differs: a failed parse loses
    one arm, but an exhausted account means every subsequent call is going to
    fail too, and the run should stop while the answer is still cheap.
    """


# 429 is here, not in the fatal set: a rate limit is the one 4xx worth waiting
# out. Distinguishing it from an exhausted balance is done on the message,
# because several vendors report both as 429.
RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
FATAL_STATUSES = frozenset({401, 402, 403})
TRANSIENT_TYPES = ("timeout", "connect", "connection", "protocol", "socket", "ssl")
RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "too many requests", "slow down")
EXHAUSTED_MARKERS = (
    "insufficient_quota", "insufficient quota", "insufficient credit",
    "insufficient funds", "out of credit", "no credits", "credit balance",
    "credits remaining", "payment required", "billing", "past due",
    "subscription", "invalid api key", "invalid_api_key", "unauthorized",
    "forbidden", "quota exceeded", "plan limit",
)


def status_of(exc: BaseException) -> int | None:
    """The HTTP status behind an exception, whatever wrapper it arrived in."""
    for attr in ("status", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    value = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(value, int):
        return value
    import re

    found = re.search(r"\b([45]\d\d)\b", str(exc))
    return int(found.group(1)) if found else None


def classify(exc: BaseException) -> tuple[int | None, str]:
    """(status, 'retry' | 'fatal' | 'fail'). What to do about a vendor error."""
    status = status_of(exc)
    text = str(exc).lower()
    name = type(exc).__name__.lower()

    # Checked before the exhausted markers: "rate limit exceeded" contains
    # "exceeded" and must not be read as an empty account.
    rate_limited = any(marker in text for marker in RATE_LIMIT_MARKERS)
    if any(marker in text for marker in EXHAUSTED_MARKERS) and not rate_limited:
        return status, "fatal"
    if status in FATAL_STATUSES:
        return status, "fatal"
    if status in RETRY_STATUSES or rate_limited:
        return status, "retry"
    if status is not None and 400 <= status < 500:
        return status, "fail"          # our request is wrong; trying again cannot help
    if status is not None and status >= 500:
        # Anything else the server says went wrong on its side is weather. The
        # named 5xx above are not the whole list: a Cloudflare 520 in front of
        # OpenAI cost us the astra arm on a 96-document parse, eight documents
        # in and after a single attempt, because 520 is not 500-504 and not
        # below 500 either, so it fell through to "fail".
        return status, "retry"
    if any(word in name for word in TRANSIENT_TYPES):
        return status, "retry"
    return status, "fail"


def retry_after(exc: BaseException, attempt: int) -> float:
    """Honour the vendor's own Retry-After, else back off exponentially."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw:
        try:
            return max(1.0, min(300.0, float(raw)))
        except (TypeError, ValueError):
            pass
    import random

    return min(60.0, 2.0 ** attempt) + random.uniform(0, 1.5)


MAX_ATTEMPTS = 5


def call_vendor(arm: str, pdf: Path, *, attempts: int = MAX_ATTEMPTS,
                on_retry=None, sleep=time.sleep) -> tuple[str, dict, list[dict]]:
    """One vendor call, retried while the failure looks like weather.

    Returns the parse plus a log of every attempt that did not succeed. That log
    is what goes in the archive: one entry per try, rather than one archive
    entry per try, so a retried parse leaves a single record that says it was
    retried instead of several records that look like several parses.
    """
    log: list[dict] = []
    for attempt in range(1, attempts + 1):
        started = time.time()
        try:
            markdown, meta = VENDORS[arm](pdf)
        except Exception as exc:  # noqa: BLE001 - classified immediately below
            status, verdict = classify(exc)
            entry = {"attempt": attempt, "status": status, "verdict": verdict,
                     "error": f"{type(exc).__name__}: {str(exc)[:400]}",
                     "seconds": round(time.time() - started, 2)}
            last = attempt >= attempts
            if verdict == "retry" and not last:
                entry["retry_in"] = round(retry_after(exc, attempt), 1)
                log.append(entry)
                if on_retry:
                    on_retry(arm, entry)
                sleep(entry["retry_in"])
                continue
            log.append(entry)
            message = f"{arm} failed after {attempt} attempt(s): {exc}"
            if verdict == "fatal":
                raise FatalVendorError(message, status=status, arm=arm) from exc
            raise VendorError(message, status=status, arm=arm) from exc
        return markdown, meta, log
    raise VendorError(f"{arm}: exhausted {attempts} attempts", arm=arm)


# Anything that could carry a key. Vendor I/O is retained with local run
# artifacts, so a header logged verbatim would leak a credential to any copy.
SECRET_HEADERS = {"x-api-key", "authorization", "api-key", "token", "cookie"}


def _redact(headers: dict) -> dict:
    return {key: ("<redacted>" if key.lower() in SECRET_HEADERS else value)
            for key, value in headers.items()}


def _dump(obj) -> Any:
    """Whatever a vendor handed back, as plain JSON-able data."""
    for attr in ("model_dump", "dict", "to_dict"):
        method = getattr(obj, attr, None)
        if callable(method):
            try:
                return method()
            except Exception:  # noqa: BLE001
                pass
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:  # noqa: BLE001
        return {"repr": repr(obj)[:20000]}


def _io(request: Any, response: Any) -> dict:
    """One vendor exchange, recorded verbatim for the raw log.

    The PDF itself is referenced by name and hash rather than embedded: it is
    already in the published snapshot, and inlining it would multiply the
    archive by the number of arms.
    """
    return {"request": request, "response": response}


def _llamaparse(pdf: Path, *, tier: str, version: str, label: str) -> tuple[str, dict]:
    from llama_cloud import LlamaCloud

    from .environment import load_environment

    load_environment()
    api_key = os.environ.get("LLAMA_API_KEY") or os.environ.get("LLAMA_CLOUD_API_KEY")
    if not api_key:
        raise RuntimeError("LLAMA_API_KEY is required for llamaparse")

    client = LlamaCloud(api_key=api_key, timeout=900)
    with pdf.open("rb") as handle:
        uploaded = client.files.create(file=handle, purpose="parse")
    result = client.parsing.parse(
        file_id=uploaded.id,
        tier=tier,
        version=version,
        expand=["markdown"],
    )
    pages = getattr(getattr(result, "markdown", None), "pages", None) or []
    markdown = "\n\n".join((getattr(p, "markdown", "") or "") for p in pages)
    meta = {
        "tier": tier,
        "version": version,
        "file_id": uploaded.id,
        "job_id": getattr(result, "id", ""),
        "n_pages": len(pages),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    meta["io"] = _io(
        {"sdk": "llama_cloud", "calls": [
            {"method": "files.create", "purpose": "parse", "file": pdf.name},
            {"method": "parsing.parse", "file_id": uploaded.id, "tier": tier,
             "version": version, "expand": ["markdown"]},
        ]},
        {"files.create": _dump(uploaded), "parsing.parse": _dump(result)},
    )
    return markdown, meta


def parse_llamaparse(pdf: Path) -> tuple[str, dict]:
    return _llamaparse(pdf, tier=LLAMAPARSE_TIER, version=LLAMAPARSE_VERSION,
                       label="llamaparse")


def parse_llamaparse_plus(pdf: Path) -> tuple[str, dict]:
    return _llamaparse(pdf, tier=LLAMAPARSE_PLUS_TIER, version=LLAMAPARSE_PLUS_VERSION,
                       label="llamaparse-plus")


def parse_reducto(pdf: Path) -> tuple[str, dict]:
    from reducto import Reducto

    from .environment import load_environment

    load_environment()
    api_key = os.environ.get("REDUCTO_API_KEY")
    if not api_key:
        raise RuntimeError("REDUCTO_API_KEY is required for reducto")

    client = Reducto(api_key=api_key, timeout=900)
    with pdf.open("rb") as handle:
        uploaded = client.upload(file=handle)
    result = client.parse.run(input=uploaded.file_id, settings={"model": REDUCTO_MODEL},
                              formatting=REDUCTO_FORMATTING)

    payload = result.model_dump() if hasattr(result, "model_dump") else {}
    chunks = ((payload.get("result") or {}).get("chunks")) or []
    markdown = "\n\n".join(str(chunk.get("content") or "") for chunk in chunks)
    # Billing lives under `usage`, not `document_properties`, which comes back
    # empty on r-1 -- reading the wrong one left this the only vendor whose cost
    # could not be checked against its own response.
    usage = payload.get("usage") or {}
    meta = {
        "model": REDUCTO_MODEL,
        "formatting": REDUCTO_FORMATTING,
        "file_id": uploaded.file_id,
        "job_id": payload.get("job_id", ""),
        "n_chunks": len(chunks),
        "n_pages": usage.get("num_pages")
                   or (payload.get("document_properties") or {}).get("num_pages", 0),
        "credits": usage.get("credits", 0),
        "credit_breakdown": usage.get("credit_breakdown"),
        "duration_s": payload.get("duration", 0),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    meta["io"] = _io(
        {"sdk": "reducto", "calls": [
            {"method": "upload", "file": pdf.name},
            {"method": "parse.run", "input": uploaded.file_id,
             "settings": {"model": REDUCTO_MODEL}, "formatting": REDUCTO_FORMATTING},
        ]},
        {"upload": _dump(uploaded), "parse.run": payload},
    )
    return markdown, meta


def parse_extend(pdf: Path) -> tuple[str, dict]:
    from extend_ai import Extend

    from .environment import load_environment

    load_environment()
    api_key = os.environ.get("EXTEND_API_KEY")
    if not api_key:
        raise RuntimeError("EXTEND_API_KEY is required for extend")

    client = Extend(token=api_key, timeout=900)
    with pdf.open("rb") as handle:
        uploaded = client.files.upload(file=handle)
    result = client.parse(file={"id": uploaded.id},
                          config={"engine": EXTEND_ENGINE, "advancedOptions": EXTEND_ADVANCED})

    payload = result.model_dump() if hasattr(result, "model_dump") else {}
    chunks = ((payload.get("output") or {}).get("chunks")) or []
    markdown = "\n\n".join(str(chunk.get("content") or "") for chunk in chunks)
    metrics = payload.get("metrics") or {}
    usage = payload.get("usage") or {}
    meta = {
        "engine": EXTEND_ENGINE,
        "advanced_options": EXTEND_ADVANCED,
        "file_id": getattr(uploaded, "id", ""),
        "job_id": payload.get("id", ""),
        "n_chunks": len(chunks),
        # pageCount has come back 0; usage.pageCount is the fallback, and the
        # credits below are billed per page either way.
        "n_pages": metrics.get("pageCount") or usage.get("pageCount") or 0,
        "duration_s": round(metrics.get("processingTimeMs", 0) / 1000, 2),
        "credits": usage.get("credits", 0),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    meta["io"] = _io(
        {"sdk": "extend_ai", "calls": [
            {"method": "files.upload", "file": pdf.name},
            {"method": "parse", "file": {"id": getattr(uploaded, "id", "")},
             "config": {"engine": EXTEND_ENGINE, "advancedOptions": EXTEND_ADVANCED}},
        ]},
        {"files.upload": _dump(uploaded), "parse": payload},
    )
    return markdown, meta


def parse_mistral(pdf: Path) -> tuple[str, dict]:
    """Mistral OCR, one synchronous call for the whole contract.

    The PDF goes inline as a base64 data URI rather than through the files API,
    which is what the endpoint documents for a document you do not intend to
    keep, and it means the arm has no upload step to fail at. Our largest
    contract is under a megabyte, so there is nothing here that needs chunking.

    Markdown comes back per page and is joined in order. Mistral does emit
    `~~struck~~`, which is why the arm is worth running -- but it emits far less
    of it than the source carries, so expect it to place well above the blind
    floor and well below a parser built for tracked changes.
    """
    import base64

    import httpx

    from .environment import load_environment

    load_environment()
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is required for mistral")

    body = {
        "model": MISTRAL_MODEL,
        "document": {
            "type": "document_url",
            "document_url": "data:application/pdf;base64,"
                            + base64.b64encode(pdf.read_bytes()).decode("ascii"),
        },
        "include_image_base64": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = httpx.post(MISTRAL_URL, headers=headers, json=body, timeout=1800)
    if response.status_code >= 400:
        raise VendorError(f"mistral-ocr {response.status_code}: {response.text[:400]}",
                          status=response.status_code, arm="mistral-ocr")
    payload = response.json()

    pages = payload.get("pages") or []
    markdown = "\n\n".join(page.get("markdown") or "" for page in pages).strip()
    if not markdown:
        raise RuntimeError(f"mistral returned no markdown; keys={sorted(payload)}")

    usage = payload.get("usage_info") or {}
    meta = {
        "model": payload.get("model") or MISTRAL_MODEL,
        "n_pages": usage.get("pages_processed") or len(pages),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    # The document is echoed back inside the request, and it is a megabyte of
    # base64. Record what was sent without re-recording the contract itself.
    meta["io"] = _io(
        {"method": "POST", "url": MISTRAL_URL, "headers": _redact(headers),
         "body": {**body, "document": {"type": "document_url",
                                       "document_url": f"<base64 {pdf.name}>"}}},
        {"status": response.status_code, "headers": dict(response.headers),
         "body": {**payload, "pages": f"<{len(pages)} pages of markdown>"}},
    )
    return markdown, meta


def parse_pulse(pdf: Path) -> tuple[str, dict]:
    import httpx

    from .environment import load_environment

    load_environment()
    api_key = os.environ.get("PULSE_API_KEY")
    if not api_key:
        raise RuntimeError("PULSE_API_KEY is required for pulse")

    data = {"model": PULSE_MODEL, "refine_options": json.dumps(PULSE_REFINE)}
    headers = {"x-api-key": api_key}
    with pdf.open("rb") as handle:
        response = httpx.post(
            PULSE_URL,
            headers=headers,
            data=data,
            files={"file": (pdf.name, handle, "application/pdf")},
            timeout=1800,
        )
    if response.status_code >= 400:
        raise VendorError(f"pulse {response.status_code}: {response.text[:400]}",
                          status=response.status_code, arm="pulse")
    payload = response.json()

    markdown = payload.get("markdown") or payload.get("text") or ""
    if not markdown and payload.get("is_url") and payload.get("url"):
        # Past some size Pulse stops inlining the result and hands back a link
        # to it instead. Not following it read as "the vendor produced nothing",
        # which on a scanned contract looks exactly like a parser that failed at
        # the task rather than a client that stopped one call short.
        fetched = httpx.get(payload["url"], timeout=1800)
        if fetched.status_code >= 400:
            raise VendorError(f"pulse result {fetched.status_code}: {fetched.text[:400]}",
                              status=fetched.status_code, arm="pulse")
        try:
            body = fetched.json()
        except ValueError:
            body = {}
        markdown = (body.get("markdown") or body.get("text") or "") if isinstance(body, dict) else ""
        if not markdown:
            markdown = fetched.text
        payload = {**payload, **(body if isinstance(body, dict) else {})}
    if not markdown:
        raise RuntimeError(f"pulse returned no markdown; keys={sorted(payload)}")

    meta = {
        "model": PULSE_MODEL,
        "refine_options": PULSE_REFINE,
        "extraction_id": payload.get("extraction_id", ""),
        "n_pages": payload.get("page_count", 0),
        "credits": payload.get("credits_used", 0),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    meta["io"] = _io(
        {"method": "POST", "url": PULSE_URL, "headers": _redact(headers),
         "data": data, "files": {"file": pdf.name}},
        {"status": response.status_code, "headers": dict(response.headers),
         "body": payload},
    )
    return markdown, meta


def _datalab_call(pdf: Path, url: str, data: dict, label: str) -> tuple[str, dict]:
    """Submit to a Datalab endpoint and poll until the conversion completes."""
    import time

    import httpx

    from .environment import load_environment

    load_environment()
    api_key = os.environ.get("DATALAB_API_KEY")
    if not api_key:
        raise RuntimeError("DATALAB_API_KEY is required for datalab")

    headers = {"X-API-Key": api_key}
    with pdf.open("rb") as handle:
        response = httpx.post(
            url,
            headers=headers,
            data=data,
            files={"file": (pdf.name, handle, "application/pdf")},
            timeout=300,
        )
    if response.status_code >= 400:
        raise VendorError(f"{label} {response.status_code}: {response.text[:400]}",
                          status=response.status_code, arm=label)
    submitted = response.json()
    check_url = submitted.get("request_check_url")
    if not check_url:
        raise RuntimeError(f"{label} gave no check url: {str(submitted)[:300]}")

    deadline = time.time() + DATALAB_MAX_WAIT
    polls: list[dict] = []
    while True:
        time.sleep(DATALAB_POLL_SECONDS)
        polled = httpx.get(check_url, headers=headers, timeout=120).json()
        # Every poll is kept, but only the last one carries the markdown, so
        # the earlier ones are recorded as status alone rather than in full.
        polls.append({"n": len(polls) + 1, "status": polled.get("status")})
        status = polled.get("status")
        if status == "complete":
            break
        if status == "failed" or polled.get("success") is False:
            raise VendorError(f"{label} failed: {polled.get('error')}", arm=label)
        if time.time() > deadline:
            raise VendorError(f"{label} timed out after {DATALAB_MAX_WAIT}s", arm=label)

    markdown = polled.get("markdown") or ""
    if not markdown:
        raise RuntimeError(f"{label} returned no markdown; keys={sorted(polled)}")

    meta = {
        "request_id": submitted.get("request_id", ""),
        "n_pages": polled.get("page_count", 0),
        "quality_score": polled.get("parse_quality_score"),
        "cost_cents": polled.get("cost_breakdown"),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    meta["io"] = _io(
        {"submit": {"method": "POST", "url": url, "headers": _redact(headers),
                    "data": data, "files": {"file": pdf.name}},
         "poll": {"method": "GET", "url": check_url, "headers": _redact(headers),
                  "every_seconds": DATALAB_POLL_SECONDS}},
        {"submit": {"status": response.status_code, "body": submitted},
         "polls": polls, "final": polled},
    )
    return markdown, meta


def parse_datalab(pdf: Path) -> tuple[str, dict]:
    markdown, meta = _datalab_call(
        pdf,
        DATALAB_URL,
        {"output_format": "markdown", "mode": DATALAB_MODE},
        "datalab",
    )
    meta["mode"] = DATALAB_MODE
    return markdown, meta


def parse_datalab_tc(pdf: Path) -> tuple[str, dict]:
    return _datalab_call(
        pdf,
        DATALAB_TC_URL,
        {"output_format": "markdown"},
        "datalab-tc",
    )


def parse_astra(pdf: Path) -> tuple[str, dict]:
    """GPT-6 Astra, one Responses call with the PDF attached.

    `input_file` takes the contract whole and lets OpenAI rasterise it, which is
    the point: the arm is measuring the model's reading of a document, not our
    choice of DPI.

    The native API is pinned rather than inherited. Foundry deployments carry
    their own model list and their own per-token rates, and an arm whose bill
    depends on which endpoint happened to be configured is not a number worth
    publishing -- so this asks for OpenAI directly and says so if it cannot.
    """
    import base64

    from .environment import PROVIDER_ENV, load_environment

    load_environment()
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(f"OPENAI_API_KEY is required for astra; "
                           f"set {PROVIDER_ENV}=openai to pin the native API")

    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=1800, max_retries=0)
    data_uri = ("data:application/pdf;base64,"
                + base64.b64encode(pdf.read_bytes()).decode("ascii"))
    content = [
        {"type": "input_text", "text": VLM_PROMPT},
        {"type": "input_file", "filename": pdf.name, "file_data": data_uri},
    ]
    try:
        response = client.responses.create(
            model=ASTRA_MODEL, input=[{"role": "user", "content": content}],
        )
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        if status:
            raise VendorError(f"astra {status}: {str(exc)[:400]}",
                              status=status, arm="astra") from exc
        raise

    markdown = (getattr(response, "output_text", "") or "").strip()
    if not markdown:
        raise RuntimeError("astra returned no text")
    # A truncated parse is the dangerous failure on this board: it returns
    # plausible markdown for the first N pages and scores as a bad parser rather
    # than as a broken call. Fail loudly instead.
    if getattr(response, "status", None) == "incomplete":
        reason = getattr(getattr(response, "incomplete_details", None), "reason", "")
        raise RuntimeError(f"astra parse incomplete ({reason}); "
                           f"{len(markdown)} chars returned for {pdf.name}")

    from .environment import usage_of

    usage = usage_of(response)
    meta = {
        "model": getattr(response, "model", None) or ASTRA_MODEL,
        "n_pages": _page_count(pdf),
        "usage": usage,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    # The request carries a megabyte of base64. Record its shape, not the file.
    meta["io"] = _io(
        {"sdk": "openai", "method": "responses.create", "model": ASTRA_MODEL,
         "input": [{"role": "user", "content": [
             {"type": "input_text", "text": VLM_PROMPT},
             {"type": "input_file", "filename": pdf.name,
              "file_data": f"<base64 {pdf.name}>"}]}]},
        {**_dump(response), "output": "<markdown returned above>"},
    )
    return markdown, meta


def _fable_client():
    """Bedrock runtime client for parsing, with a parse-length read timeout.

    Credentials come from the web-search judge's loader, which already knows the
    cascade (this repo's .env, then the sibling backend's); only the transport
    config differs.
    """
    global _FABLE_CLIENT
    if _FABLE_CLIENT is not None:
        return _FABLE_CLIENT

    import boto3
    from botocore.config import Config

    from websearch.bedrock_judge import load_bedrock_environment

    load_bedrock_environment()
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") \
        or "us-east-1"
    config = Config(retries={"max_attempts": 1}, read_timeout=FABLE_READ_TIMEOUT,
                    connect_timeout=10)
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if access_key and secret_key:
        session = boto3.Session(aws_access_key_id=access_key,
                                aws_secret_access_key=secret_key, region_name=region)
        _FABLE_CLIENT = session.client("bedrock-runtime", config=config)
    else:
        _FABLE_CLIENT = boto3.client("bedrock-runtime", region_name=region, config=config)
    return _FABLE_CLIENT


def parse_fable(pdf: Path) -> tuple[str, dict]:
    """Claude Fable 5.1 on Bedrock, one converse call with the PDF attached.

    Two things about this model are not shared with the others. It reasons
    always-on and non-optionally, so the reply arrives as `reasoningContent`
    followed by `text` and the markdown has to be picked out of the block list
    rather than read off index 0 -- and those thinking tokens are billed as
    output, which is most of why the arm costs what it does. And `temperature`
    is rejected outright on Opus 4.7 and later, so inferenceConfig carries only
    a token ceiling; there is no determinism knob to set.

    Fable additionally refuses to run unless the account's Bedrock data
    retention mode is `provider_data_share`, meaning prompts are shared with
    Anthropic and held up to 30 days. That is an account-level setting this code
    cannot make on its own, so the failure is named rather than retried.
    """
    client = _fable_client()
    body = {
        "modelId": FABLE_MODEL,
        "messages": [{"role": "user", "content": [
            {"text": VLM_PROMPT},
            {"document": {"format": "pdf", "name": "contract",
                          "source": {"bytes": pdf.read_bytes()}}},
        ]}],
        "inferenceConfig": {"maxTokens": FABLE_MAX_TOKENS},
    }
    try:
        response = client.converse(**body)
    except Exception as exc:  # noqa: BLE001
        if "data retention mode" in str(exc):
            raise VendorError(
                "fable: Bedrock account data retention must be "
                "'provider_data_share' (aws bedrock put-account-data-retention "
                f"--mode provider_data_share): {str(exc)[:200]}",
                status=403, arm="fable") from exc
        status = (getattr(exc, "response", {}) or {}).get(
            "ResponseMetadata", {}).get("HTTPStatusCode")
        if status:
            raise VendorError(f"fable {status}: {str(exc)[:400]}",
                              status=status, arm="fable") from exc
        raise

    blocks = response["output"]["message"]["content"]
    markdown = "".join(b["text"] for b in blocks if "text" in b).strip()
    if not markdown:
        raise RuntimeError(f"fable returned no text; blocks={[list(b) for b in blocks]}")
    if response.get("stopReason") == "max_tokens":
        raise RuntimeError(f"fable parse truncated at {FABLE_MAX_TOKENS} output "
                           f"tokens; {len(markdown)} chars returned for {pdf.name}")

    tokens = response.get("usage") or {}
    meta = {
        "model": FABLE_MODEL,
        "n_pages": _page_count(pdf),
        # Normalised to the Responses API's names so cost_of_parse can price
        # both frontier arms through one code path.
        "usage": {"input_tokens": tokens.get("inputTokens") or 0,
                  "output_tokens": tokens.get("outputTokens") or 0},
        "stop_reason": response.get("stopReason"),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    meta["io"] = _io(
        {"sdk": "boto3", "method": "bedrock-runtime.converse", **{
            **body, "messages": [{"role": "user", "content": [
                {"text": VLM_PROMPT},
                {"document": {"format": "pdf", "name": "contract",
                              "source": f"<{pdf.name} bytes>"}}]}]}},
        {**_dump(response), "output": "<markdown returned above>"},
    )
    return markdown, meta


# Both LlamaParse tiers run. `llamaparse-plus` was measured alone for a while,
# on the reasoning that a vendor should be judged at its best setting -- but the
# two Datalab endpoints are on the board fifteen points apart precisely to show
# what a setting is worth, and the same question is worth answering here: what
# does agentic_plus buy over agentic on a redline, and is it worth 4.5x the page
# rate. That is a measurement, not a footnote, so the cheaper tier is back.


VENDORS = {
    "llamaparse": parse_llamaparse,
    "llamaparse-plus": parse_llamaparse_plus,
    "reducto": parse_reducto,
    "extend": parse_extend,
    "pulse": parse_pulse,
    "mistral-ocr": parse_mistral,
    "datalab": parse_datalab,
    "datalab-tc": parse_datalab_tc,
    "astra": parse_astra,
    "fable": parse_fable,
}

# Every knob that changes what a vendor returns. The cache is keyed on this as
# well as the PDF, because a parse made under different settings is a different
# measurement, and serving it from cache would put a stale number on the board.
SETTINGS: dict[str, dict] = {
    "llamaparse": {"tier": LLAMAPARSE_TIER, "version": LLAMAPARSE_VERSION},
    "llamaparse-plus": {"tier": LLAMAPARSE_PLUS_TIER, "version": LLAMAPARSE_PLUS_VERSION},
    "reducto": {"model": REDUCTO_MODEL, "formatting": REDUCTO_FORMATTING,
                "build": REDUCTO_BUILD},
    "extend": {"engine": EXTEND_ENGINE, "advanced_options": EXTEND_ADVANCED},
    "pulse": {"model": PULSE_MODEL, "refine_options": PULSE_REFINE},
    "mistral-ocr": {"model": MISTRAL_MODEL},
    "datalab": {"url": DATALAB_URL, "mode": DATALAB_MODE},
    "datalab-tc": {"url": DATALAB_TC_URL},
    # The prompt is a setting here in the way a formatting flag is for a vendor,
    # so it is fingerprinted: reword it and every cached frontier parse rightly
    # misses, because it is no longer the same measurement.
    "astra": {"model": ASTRA_MODEL, "input": "pdf", "prompt": VLM_PROMPT},
    "fable": {"model": FABLE_MODEL, "input": "pdf", "prompt": VLM_PROMPT,
              "max_tokens": FABLE_MAX_TOKENS},
}

ARMS = REFERENCE_ARMS + tuple(sorted(VENDORS))

# Whether this arm had to be *asked* for tracked changes. The single most
# important fact about any number on this board: on four of these ten vendors
# the strike survives only because a flag above is set, and an arm run without
# it measures the flag rather than the parser. Surfaced per case in the trace so
# a low score can be read as "worse parse" or "different configuration" without
# going back to the source.
TRACKED_CHANGES_OPT_IN = {
    "astra": False,            # VLM_PROMPT does not mention strikethrough
    "fable": False,            # same prompt, same answer
    "datalab": False,          # general convert endpoint, no such flag
    "datalab-tc": True,        # a dedicated /track-changes endpoint
    "extend": True,            # advancedOptions.formattingDetection
    "llamaparse": False,       # emits ~~ in default markdown, nothing to enable
    "llamaparse-plus": False,  # same
    "mistral-ocr": False,      # OCR endpoint has no such flag; emits ~~ or not
    "pulse": True,             # refine_options.formatting
    "reducto": True,           # formatting.include = change_tracking
}


def tracked_changes(arm: str) -> bool | None:
    """True/False for a vendor, None for a reference arm where it means nothing."""
    return TRACKED_CHANGES_OPT_IN.get(arm) if arm not in REFERENCE_ARMS else None


# Who each arm belongs to, and what distinguishes it from its siblings.
#
# Several vendors appear more than once -- Datalab as two endpoints, LlamaParse
# as two tiers -- and the arm slug alone does not say so. Without this, two rows
# of one vendor read as two vendors, a per-vendor bill cannot be totalled, and
# nothing records that those two rows share an API, an account and a rate limit.
# `variant` is the setting that makes the arm a distinct measurement, and it is
# the human-readable form of what settings_fingerprint() hashes.
IDENTITY: dict[str, dict[str, str]] = {
    "oracle":          {"vendor": "reference", "variant": "struck text kept as ~~…~~"},
    "blind":           {"vendor": "reference", "variant": "all markup dropped"},
    "accepted":        {"vendor": "reference", "variant": "edits applied"},
    "datalab":         {"vendor": "Datalab", "variant": "convert · mode=accurate"},
    "datalab-tc":      {"vendor": "Datalab", "variant": "track-changes endpoint"},
    "extend":          {"vendor": "Extend", "variant": f"engine={EXTEND_ENGINE}"},
    "llamaparse":      {"vendor": "LlamaParse",
                        "variant": f"tier={LLAMAPARSE_TIER} · {LLAMAPARSE_VERSION}"},
    "llamaparse-plus": {"vendor": "LlamaParse",
                        "variant": f"tier={LLAMAPARSE_PLUS_TIER} · {LLAMAPARSE_PLUS_VERSION}"},
    "astra":           {"vendor": "OpenAI", "variant": f"{ASTRA_MODEL} · pdf in"},
    "fable":           {"vendor": "Anthropic",
                        "variant": "claude-fable-5-1 · pdf in · bedrock"},
    "pulse":           {"vendor": "Pulse", "variant": f"model={PULSE_MODEL}"},
    "mistral-ocr":     {"vendor": "Mistral", "variant": f"model={MISTRAL_MODEL}"},
    "reducto":         {"vendor": "Reducto",
                        "variant": f"model={REDUCTO_MODEL} · {REDUCTO_BUILD} build"},
}


def identity(arm: str) -> dict[str, str]:
    return IDENTITY.get(arm, {"vendor": arm, "variant": ""})


def vendor_of(arm: str) -> str:
    return identity(arm)["vendor"]


# How many documents may be in flight at one vendor at once. One by default:
# this measures how a parser reads a redline, not how it survives a stampede,
# and a vendor that 429s mid-run loses its whole arm.
#
# The exception is a limit the vendor publishes itself. LlamaCloud states a
# plan quota of 5 concurrent parse jobs, so running 4 is operating inside a
# documented allowance rather than guessing at what is polite -- and LlamaParse
# is the slowest arm by a wide margin, at roughly 110s per contract against
# Reducto's 8. Keyed by vendor and not by arm: two arms of one vendor share one
# account and one quota, so five each would be ten jobs and a breach.
#
# Widening this makes the `seconds` recorded on a parse a queued figure rather
# than a clean latency, which is why it stays at 1 everywhere it is not needed.
#
# The frontier arms get 4 for the same reason and with the same kind of
# evidence. They are the slowest arms on the board by far -- a whole contract in
# one call, measured at 373s (Astra) and 518s (Fable) on the 38-page worst case,
# against Reducto's 8s -- so serial they would take most of a day. Four
# concurrent documents is far inside both published allowances: Bedrock's
# default is 2M input TPM and 500k output TPM, and four Fable contracts in
# flight is roughly 50k input and 26k output per minute. Neither vendor is
# near a limit; the ceiling here is patience, not quota.
VENDOR_CONCURRENCY = {"LlamaParse": 4, "OpenAI": 4, "Anthropic": 4}


def concurrency_for(arm: str) -> int:
    return VENDOR_CONCURRENCY.get(vendor_of(arm), 1)


def siblings(arm: str) -> list[str]:
    """Other arms billed to the same vendor. Empty for a vendor run once."""
    vendor = vendor_of(arm)
    if vendor == "reference":
        return []
    return [name for name in sorted(IDENTITY)
            if name != arm and IDENTITY[name]["vendor"] == vendor]


def settings_fingerprint(arm: str) -> str:
    payload = json.dumps(SETTINGS.get(arm, {}), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def cache_paths(cache_dir: Path, document_id: str, arm: str) -> tuple[Path, Path]:
    return cache_dir / f"{document_id}.{arm}.md", cache_dir / f"{document_id}.{arm}.meta.json"


def io_path(cache_dir: Path, document_id: str, arm: str) -> Path:
    """Where the verbatim vendor exchange for one parse lives.

    Gzipped because these are the largest artefacts the harness produces --
    a Reducto or Extend body carries every chunk with its bounding boxes, and
    there is one per document per arm.
    """
    return cache_dir / f"{document_id}.{arm}.io.json.gz"


def write_io(cache_dir: Path, document_id: str, arm: str, io: dict) -> Path:
    import gzip

    path = io_path(cache_dir, document_id, arm)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(io, handle, default=str)
    return path


def render(document, arm: str, cache_dir: Path, *, force: bool = False,
           on_retry=None) -> tuple[str, dict]:
    """Markdown for one document under one arm, plus what it cost to get."""
    if arm in REFERENCE_ARMS:
        path = document.views.get(arm)
        if not path or not path.is_file():
            raise SystemExit(f"{document.document_id}: snapshot has no {arm} view")
        text = path.read_text(encoding="utf-8")
        return text, {"arm": arm, **identity(arm), "reference": True, "cached": True,
                      "markdown_chars": len(text)}

    if arm not in VENDORS:
        raise SystemExit(f"unknown arm {arm!r}; choose from {', '.join(ARMS)}")

    pdf = document.pdf
    md_path, meta_path = cache_paths(cache_dir, document.document_id, arm)
    digest = sha256(pdf)
    fingerprint = settings_fingerprint(arm)
    if md_path.is_file() and meta_path.is_file() and not force:
        meta = json.loads(meta_path.read_text())
        if meta.get("pdf_sha256") == digest and meta.get("settings_sha256") == fingerprint:
            # Stamped on read as well as on write, so a cache filled before this
            # existed still reports which vendor and variant produced it.
            meta.update({"cached": True, **identity(arm)})
            return md_path.read_text(encoding="utf-8"), meta

    started = time.time()
    markdown, meta, attempts = call_vendor(arm, pdf, on_retry=on_retry)
    # The verbatim exchange is bulky and is wanted in the archive rather than in
    # every meta.json the cache reads, so it goes to its own file next to it.
    exchange = meta.pop("io", None)
    # Wall clock around the whole call, including any polling. Some vendors
    # report their own processing time and some report nothing, so this is the
    # only latency figure that means the same thing across all seven.
    elapsed = round(time.time() - started, 2)
    meta.update({
        "arm": arm,
        **identity(arm),
        # Derived rather than hardcoded false: the tag reader is dispatched
        # like a vendor so it gets the cache and the timing, but nothing was
        # billed, and pricing keys zero cost off this flag.
        "reference": vendor_of(arm) == "reference",
        "seconds": elapsed,
        "markdown_file": md_path.name,
        "pdf": pdf.name,
        "pdf_sha256": digest,
        "pdf_bytes": pdf.stat().st_size,
        "settings": SETTINGS.get(arm, {}),
        "settings_sha256": fingerprint,
        "markdown_chars": len(markdown),
        "cached": False,
    })
    if attempts:
        # One record that says it was retried, rather than one record per try.
        meta["retries"] = len(attempts)
        exchange = exchange or {}
        exchange["attempts"] = attempts

    cache_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    if exchange is not None:
        written = write_io(cache_dir, document.document_id, arm, exchange)
        meta["io_file"] = written.name
        meta["io_bytes"] = written.stat().st_size
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return markdown, meta
