from __future__ import annotations

NO_CHOICES_RETURNED = "No choices returned in the response."


def rate_limit_exceeded(max_retries: int, error: Exception) -> str:
    return f"Rate limit exceeded after {max_retries} attempts: {error}"


def api_error(error: Exception) -> str:
    return f"API error occurred: {error}"


def unexpected_error(error: Exception) -> str:
    return f"An unexpected error occurred: {error}"
