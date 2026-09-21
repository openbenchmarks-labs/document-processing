from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROVIDER_ENV = "DOC_PROCESSING_LLM_PROVIDER"
DEFAULT_MODEL = "gpt-5.6-sol"


def load_environment() -> None:
    for name in (".env.local", ".env"):
        load_dotenv(Path.cwd() / name, override=False)


def make_llm_client(*, timeout: float = 180, max_retries: int = 5) -> Any:
    load_environment()
    from openai import OpenAI

    provider = (os.environ.get(PROVIDER_ENV) or "").lower()
    azure_url = (os.environ.get("AZURE_OPENAI_NEXTGEN_DEPLOYMENT_URL") or "").rstrip("/")
    azure_key = os.environ.get("AZURE_OPENAI_NEXTGEN_DEPLOYMENT_KEY") or ""
    if azure_url and azure_key and provider != "openai":
        return OpenAI(base_url=azure_url, api_key=azure_key, timeout=timeout,
                      max_retries=max_retries)
    key = os.environ.get("OPENAI_API_KEY") or ""
    if not key:
        raise SystemExit("set OPENAI_API_KEY (or the documented Azure endpoint variables)")
    return OpenAI(api_key=key, timeout=timeout, max_retries=max_retries)


def usage_of(response: Any) -> dict:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return {key: getattr(usage, key) for key in
            ("input_tokens", "output_tokens", "total_tokens")
            if getattr(usage, key, None) is not None}
