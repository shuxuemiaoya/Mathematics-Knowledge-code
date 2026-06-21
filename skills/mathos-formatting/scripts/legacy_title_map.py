from __future__ import annotations

from mathos_common import parse_python_source_artifact, validate_title_rewrite_source


def run_heading_optimization(
    markdown: str,
    provider_client: object,
    prompt: str,
    timeout_seconds: int = 120,
) -> dict[str, str]:
    heading_lines = [line.strip() for line in markdown.splitlines() if line.strip().startswith("#")]
    if not heading_lines:
        return {}
    input_payload = "\n".join(heading_lines)
    try:
        response = provider_client.chat(
            prompt, input_payload, timeout_seconds=timeout_seconds, response_format=None
        )
        return validate_title_rewrite_source(parse_python_source_artifact(response))
    except Exception:
        return {}


def apply_title_rewrite_map(markdown: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return markdown
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in mapping:
            lines[index] = line.replace(stripped, mapping[stripped])
    return "\n".join(lines) + "\n"
