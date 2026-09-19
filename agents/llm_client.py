"""Provider-agnostic LLM client with Pydantic structured outputs."""

from __future__ import annotations

import os
import json
import logging
from typing import TypeVar, Type
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def get_provider() -> str:
    """Gets the configured LLM provider from environment."""
    return os.getenv("LLM_PROVIDER", "openai").lower().strip()


def complete(
    system: str,
    user: str,
    schema: Type[T],
    temperature: float = 0.7,
    provider: str | None = None,
) -> T:
    """Runs a structured-output call against whichever provider is configured.
    Returns an instance of the given Pydantic schema.
    """
    selected_provider = (provider or get_provider()).lower()
    if selected_provider == "anthropic":
        return _complete_anthropic(system, user, schema, temperature)
    elif selected_provider == "openai":
        return _complete_openai(system, user, schema, temperature)
    else:
        raise ValueError(
            f"Unknown or unsupported LLM_PROVIDER: '{selected_provider}'. "
            f"Must be 'openai' or 'anthropic'."
        )


def _complete_openai(system: str, user: str, schema: Type[T], temperature: float) -> T:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set in .env")

    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    timeout = float(os.getenv("OPENAI_TIMEOUT", "15.0"))
    client = OpenAI(api_key=api_key, timeout=timeout)

    logger.debug("Calling OpenAI model %s with schema %s", model, schema.__name__)
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=schema,
        temperature=temperature,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("OpenAI failed to parse response into requested schema.")
    return parsed


def _complete_anthropic(system: str, user: str, schema: Type[T], temperature: float) -> T:
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set in .env")

    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    client = anthropic.Anthropic(api_key=api_key)

    tool_name = f"return_{schema.__name__.lower()}"
    json_schema = schema.model_json_schema()

    logger.debug("Calling Anthropic model %s with schema %s", model, schema.__name__)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[
            {
                "name": tool_name,
                "description": f"Output structured data matching {schema.__name__}",
                "input_schema": json_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return schema.model_validate(block.input)

    raise ValueError(f"Anthropic response did not contain expected tool call {tool_name}")
