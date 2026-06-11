"""Provider adapter for MathOS adaptive Markdown formatting."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib import request


class ProviderError(RuntimeError):
    """Raised when provider configuration or response parsing fails."""


@dataclass(frozen=True)
class ProviderSettings:
    api_key: str
    base_url: str
    model: str

    def __repr__(self) -> str:
        return f"ProviderSettings(api_key='<redacted>', base_url={self.base_url!r}, model={self.model!r})"


def _read_env(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        raise ProviderError(f"env file does not exist: {env_path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_provider_settings(env_path: Path) -> ProviderSettings:
    values = _read_env(env_path)
    api_key = values.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ProviderError("DEEPSEEK_API_KEY is missing")
    return ProviderSettings(
        api_key=api_key,
        base_url=values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        model=values.get("DEEPSEEK_MODEL", "deepseek-chat"),
    )


def parse_heading_rules_artifact(text: str) -> dict:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"heading rules response is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or "rules" not in payload:
        raise ProviderError("heading rules response must be a JSON object with a rules key")
    if not isinstance(payload["rules"], list):
        raise ProviderError("heading rules response rules key must be a list")
    return payload


def parse_python_artifact(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:python)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    if "def clean(" not in stripped or "def analyze(" not in stripped:
        raise ProviderError("python artifact must define analyze() and clean()")
    return stripped


def call_deepseek_chat(
    settings: ProviderSettings,
    system_prompt: str,
    user_payload: str,
    timeout_seconds: int = 120,
    response_format: dict | None = None,
) -> str:
    endpoint = f"{settings.base_url}/chat/completions"
    data_dict = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
    }
    if response_format:
        data_dict["response_format"] = response_format
    payload = json.dumps(data_dict).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
        data = json.loads(body)
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("provider response missing choices[0].message.content") from exc
    except json.JSONDecodeError as exc:
        raise ProviderError("provider response is not valid JSON") from exc


@dataclass(frozen=True)
class DeepSeekProviderClient:
    settings: ProviderSettings

    @property
    def base_url(self) -> str:
        return self.settings.base_url

    @property
    def model(self) -> str:
        return self.settings.model

    def __repr__(self) -> str:
        return f"DeepSeekProviderClient(base_url={self.base_url!r}, model={self.model!r})"

    def chat(
        self,
        system_prompt: str,
        user_payload: str,
        timeout_seconds: int = 120,
        response_format: dict | None = None,
    ) -> str:
        return call_deepseek_chat(
            self.settings,
            system_prompt,
            user_payload,
            timeout_seconds,
            response_format,
        )

