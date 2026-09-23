import tiktoken

DEFAULT_MODEL = "gpt-4o"


def get_tokenizer(model: str = DEFAULT_MODEL) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = DEFAULT_MODEL) -> int:
    encoding = get_tokenizer(model)
    return len(encoding.encode(text))


def truncate_text(
    text: str,
    max_tokens: int,
    suffix: str = "...",
    model: str = DEFAULT_MODEL,
) -> str:
    if max_tokens <= 0:
        return suffix

    encoding = get_tokenizer(model)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text

    suffix_tokens = len(encoding.encode(suffix))
    keep = max(0, max_tokens - suffix_tokens)
    return encoding.decode(tokens[:keep]) + suffix
