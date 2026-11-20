"""Structured Responses calls with usage accounting."""
import json
from threading import Lock

from openai import APIError

from .costs import log_call

_USAGE_LOCK = Lock()


def structured(client, model, stage, schema, instructions, payload):
    try:
        response = client.responses.parse(
            model=model, instructions=instructions,
            input=json.dumps(payload, ensure_ascii=False), text_format=schema, store=False,
        )
    except APIError as exc:
        with _USAGE_LOCK:
            log_call(stage, model)
        detail = exc.body.get("message") if isinstance(exc.body, dict) else None
        status = getattr(exc, "status_code", None)
        reason = detail or (exc.message if status is None else type(exc).__name__)
        raise RuntimeError(f"{stage}: {reason}" + (f" (HTTP {status})" if status else "")) from None
    usage = response.usage
    with _USAGE_LOCK:
        log_call(stage, model, usage.input_tokens if usage else 0,
                 usage.output_tokens if usage else 0)
    result = response.output_parsed
    if result is None:
        raise RuntimeError(f"{stage}: no structured output returned")
    return result
