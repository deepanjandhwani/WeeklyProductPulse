import re

PII_PATTERNS = [
    # Emails
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]'),
    # Generic numbers 10 digits or longer (covers most accounts/phones)
    (r'\b\d{10,}\b', '[NUMBER_REDACTED]'),
    # Phone numbers (common IN formats)
    (r'\+?\d{0,3}[-.\s]?\(' r'\d{2,3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE_REDACTED]'),
    # Demat/Account patterns (Alphanumeric blends)
    (r'\b[A-Z]{2,5}\d{6,}\b', '[ACCOUNT_REDACTED]'),
    # PAN India
    (r'\b[A-Z]{5}\d{4}[A-Z]\b', '[PAN_REDACTED]'),
    # Aadhaar India
    (r'\b\d{4}\s?\d{4}\s?\d{4}\b', '[AADHAAR_REDACTED]')
]

def scrub_pii(text: str) -> str:
    """
    Regex fallback to forcefully remove PII the LLM might have missed.
    This runs on the final generated text.
    """
    if not isinstance(text, str):
        return text
        
    for pattern, replacement in PII_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text
