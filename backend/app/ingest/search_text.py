import re

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# HTTPServer -> HTTP, Server | signatureExpired -> signature, Expired | v2 -> v, 2
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def split_identifier(name: str) -> list[str]:
    parts: list[str] = []
    for piece in name.split("_"):
        parts.extend(_CAMEL.findall(piece))
    return [p.lower() for p in parts if p]


def expand_identifiers(text: str) -> str:
    """Keep each identifier and add its parts: 'SignatureExpired' -> 'signatureexpired signature expired'."""
    words: list[str] = []
    for token in _IDENT.findall(text):
        parts = split_identifier(token)
        words.append(token.lower())
        if len(parts) > 1:
            words.extend(parts)
    return " ".join(words)


def build_search_text(path: str, symbol: str | None, content: str) -> str:
    # Path and symbol are included so "timed.py" or "unsign" match even if
    # the chunk body never repeats them.
    return expand_identifiers(f"{path} {symbol or ''} {content}")