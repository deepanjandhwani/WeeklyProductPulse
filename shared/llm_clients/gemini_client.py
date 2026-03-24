"""
shared/llm_clients/gemini_client.py — Helper module for calling the Gemini API.

Responsibilities
----------------
* Manage raw LLM calls to Gemini 2.x Flash-Lite API.
* Accept JSON schema extraction formats.
* Handle retries, delays, and authentication automatically.
"""

import json
import logging
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from tenacity import retry, retry_if_exception_type, wait_exponential, stop_after_attempt, before_sleep_log

import config

logger = logging.getLogger("weekly_pulse")

# Initialize the library with the API key from config.
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
else:
    logger.warning(
        "GEMINI_API_KEY not set (optional if PHASE3/PHASE4 use Groq only).",
        extra={"phase": "llm_client"},
    )

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(multiplier=config.RETRY_BASE_DELAY, min=2, max=20),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def generate_gemini_json(system_instruction: str, user_prompt: str, model_name: str = config.GEMINI_MODEL) -> dict | list | None:
    """
    Call Gemini to generate a JSON response based on prompt constraints.
    """
    if not config.GEMINI_API_KEY:
        logger.error("Cannot call Gemini without API key.")
        return None

    logger.debug(
        "Calling Gemini LLM (JSON Mode)", 
        extra={
            "phase": "llm_client", 
            "data": {"model": model_name, "prompt_length": len(system_instruction) + len(user_prompt)}
        }
    )

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction
    )

    config_opts = GenerationConfig(
        response_mime_type="application/json",
        temperature=0.0
    )

    response = model.generate_content(
        user_prompt,
        generation_config=config_opts
    )

    raw_output = response.text
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse Gemini JSON: {raw_output}", exc_info=True, extra={"phase": "llm_client"})
        raise exc


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(multiplier=config.RETRY_BASE_DELAY, min=2, max=20),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def generate_gemini_text(system_instruction: str, user_prompt: str, model_name: str = config.GEMINI_MODEL) -> str:
    """
    Call Gemini to generate a standard text (e.g. Markdown) response.
    """
    if not config.GEMINI_API_KEY:
        logger.error("Cannot call Gemini without API key.")
        return ""

    logger.debug(
        "Calling Gemini LLM (Text Mode)", 
        extra={
            "phase": "llm_client", 
            "data": {"model": model_name}
        }
    )

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction
    )
    
    config_opts = GenerationConfig(
        temperature=0.4
    )

    response = model.generate_content(
        user_prompt,
        generation_config=config_opts
    )

    return response.text
