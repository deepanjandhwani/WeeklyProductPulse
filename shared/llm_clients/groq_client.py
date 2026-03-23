"""
shared/llm_clients/groq_client.py — Helper module for calling the Groq LLM API.

Responsibilities
----------------
* Manage raw LLM calls to Groq API.
* Enforce deterministic JSON output using prompt strictness or JSON mode.
* Handle retries, delays, and authentication automatically.
"""

import json
import logging
from typing import Any
from groq import Groq
from tenacity import retry, retry_if_exception_type, wait_exponential, stop_after_attempt, before_sleep_log

import config

logger = logging.getLogger("weekly_pulse")

# Initialize the client. The groq library naturally reads the `GROQ_API_KEY` env var.
try:
    _client = Groq(api_key=config.GROQ_API_KEY)
except Exception as e:
    _client = None
    logger.error(f"Failed to initialize Groq client: {e}", extra={"phase": "llm_client"})

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(multiplier=config.RETRY_BASE_DELAY, min=2, max=20),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def generate_json_response(system_prompt: str, user_prompt: str, model: str = config.GROQ_MODEL) -> dict | list | None:
    """
    Call Groq to generate a JSON response based on prompt constraints.
    
    Args:
        system_prompt: The rigid instructions defining the JSON array/object structure.
        user_prompt: The batch of text data for the LLM.
        model: The model to use (default: llama-3.3-70b-versatile).

    Returns:
        A parsed Python dictionary or list, or None if formatting fails.
    """
    if not _client:
        logger.error("Groq client not initialized. Is GROQ_API_KEY set?", extra={"phase": "llm_client"})
        return None

    logger.debug(
        "Calling Groq LLM", 
        extra={
            "phase": "llm_client", 
            "data": {"model": model, "prompt_length": len(system_prompt) + len(user_prompt)}
        }
    )

    response = _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.0,  # Strictly deterministic mapping
        response_format={"type": "json_object"}
    )

    raw_output = response.choices[0].message.content
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as exc:
        logger.error(
            f"Failed to parse LLM JSON output. Output: {raw_output}", 
            exc_info=True, 
            extra={"phase": "llm_client"}
        )
        raise exc  # Re-raise to trigger tenacity retry
