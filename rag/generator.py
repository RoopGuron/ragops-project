"""Stage 3: call the LLM with the built prompt, return answer text + usage.

Thin wrapper over the Anthropic Messages API — kept small and free of RAG
logic so answer.py's tests can mock it. The model id comes from RagConfig
(default claude-opus-5); Week 2 logs it as an MLflow param and may swap in a
cheaper model (claude-sonnet-5 / claude-haiku-4-5) for the eval sweeps.

No extended thinking: this is short grounded extraction, not multi-step
reasoning. The call is wrapped for rate-limit / API errors because --eval
mode runs it ~25 times in a loop (the SDK already retries 429/5xx twice on
its own).
"""

from dataclasses import dataclass
import os

import anthropic

from rag.config import DEFAULT_LLM_MODEL


@dataclass
class GenerationResult:
    text: str
    model: str
    stop_reason: str | None
    usage: dict


def generate(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_LLM_MODEL,
    max_tokens: int = 1024,
) -> GenerationResult:
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not workspace_id:
        raise ValueError("ANTHROPIC_WORKSPACE_ID is not set.")

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set.")

    print(f"Anthropic workspace: {workspace_id or '(none)'}, model: {model}, max_tokens: {max_tokens}")

    client = anthropic.Anthropic(
        api_key=api_key,
        default_headers={"anthropic-workspace-id": workspace_id} if workspace_id else None
    )

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.RateLimitError as e:
        raise RuntimeError(f"Anthropic rate limit hit after SDK retries: {e}") from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Anthropic API error {e.status_code}: {e.message}") from e

    text = "".join(b.text for b in resp.content if b.type == "text")
    return GenerationResult(
        text=text,
        model=resp.model,
        stop_reason=resp.stop_reason,
        usage={
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        },
    )
