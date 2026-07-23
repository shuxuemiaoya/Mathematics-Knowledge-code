# -*- coding: utf-8 -*-
"""
DeepSeek provider wrapper for Promptfoo.

Promptfoo custom Python provider that calls the DeepSeek Chat API
(OpenAI-compatible) with configurable model, temperature, and max_tokens.

Usage in promptfooconfig.yaml:
    providers:
      - id: python:providers/deepseek_provider.py

Environment:
    DEEPSEEK_API_KEY — Required API key for authentication.
"""

import json
import os
import sys
from typing import Any

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass  # Should always be available in stdlib

# ── Configuration ────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_MAX_TOKENS = 16384
DEFAULT_TEMPERATURE = 0


def call_api(
    prompt: str,
    options: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Promptfoo custom provider entry point.

    Args:
        prompt: The rendered prompt text.
        options: Provider config from promptfooconfig.yaml.
        context: Additional context (vars, test info).

    Returns:
        Dict with 'output' key (string) on success,
        or 'error' key (string) on failure.
    """
    options = options or {}
    config = options.get("config", {})

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"error": "DEEPSEEK_API_KEY environment variable is not set"}

    base_url = config.get("apiBaseUrl", DEFAULT_BASE_URL).rstrip("/")
    model = config.get("model", DEFAULT_MODEL)
    max_tokens = config.get("max_tokens", DEFAULT_MAX_TOKENS)
    temperature = config.get("temperature", DEFAULT_TEMPERATURE)

    # Build the messages payload
    messages = [{"role": "user", "content": prompt}]

    # If a system prompt is specified, prepend it
    system_prompt = config.get("system_prompt")
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    # Support reasoning_effort for v4+ models (deepseek-reasoner, etc.)
    reasoning_effort = config.get("reasoning_effort")
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort

    # Optional top_p, frequency_penalty, presence_penalty
    for param in ("top_p", "frequency_penalty", "presence_penalty"):
        if param in config:
            body[param] = config[param]

    url = f"{base_url}/v1/chat/completions"
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp_body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        return {
            "error": (
                f"DeepSeek API error {e.code}: {e.reason}\n{error_body}"
            )
        }
    except urllib.error.URLError as e:
        return {"error": f"Network error: {e.reason}"}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}

    try:
        data = json.loads(resp_body)
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON response: {resp_body[:500]}"}

    # Extract content from the first choice
    choices = data.get("choices", [])
    if not choices:
        return {"error": f"No choices in response: {resp_body[:500]}"}

    message = choices[0].get("message", {})
    content = message.get("content", "")

    # Include token usage metadata if available
    usage = data.get("usage", {})
    token_usage = {}
    if usage:
        token_usage = {
            "total": usage.get("total_tokens", 0),
            "prompt": usage.get("prompt_tokens", 0),
            "completion": usage.get("completion_tokens", 0),
        }

    result: dict[str, Any] = {"output": content}
    if token_usage:
        result["tokenUsage"] = token_usage

    return result
