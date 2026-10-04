"""
MicroScheme v2 Lexer
Spec 05 §2, §3
"""

import re
from dataclasses import dataclass
from typing import Literal

from lucca.core.exceptions import SchemeSyntaxError

TokenType = Literal["LPAREN", "RPAREN", "KEYWORD", "STRING", "NUMBER", "BOOLEAN", "SYMBOL"]


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str | int | float | bool
    line: int
    col: int


MAX_SOURCE_BYTES = 8192
MAX_TOKENS = 2000

TOKEN_SPEC = [
    ("COMMENT", r";[^\n]*"),
    ("STRING", r'"(?:[^"\\]|\\.)*"'),
    ("KEYWORD", r":[a-zA-Z][a-zA-Z0-9_-]*"),
    ("FLOAT", r"-?[0-9]+\.[0-9]+"),
    ("INT", r"-?[0-9]+"),
    ("BOOLEAN", r"#(?:t|f)(?![a-zA-Z0-9_?=<>!-])"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("SYMBOL", r"[a-zA-Z_?][a-zA-Z0-9_?=<>!-]*|[+\-*/<>=]+"),
    ("WS", r"\s+"),
    ("MISMATCH", r"."),
]

TOKEN_REGEX = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in TOKEN_SPEC))


def _unescape_scheme_string(raw: str, line: int, col: int) -> str:
    res: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == "\\":
            if i + 1 >= n:
                raise SchemeSyntaxError("Trailing backslash in string literal", line, col)
            nxt = raw[i + 1]
            if nxt == '"':
                res.append('"')
            elif nxt == "\\":
                res.append("\\")
            elif nxt == "n":
                res.append("\n")
            elif nxt == "t":
                res.append("\t")
            else:
                raise SchemeSyntaxError(f"Invalid escape sequence \\{nxt}", line, col)
            i += 2
        else:
            res.append(c)
            i += 1
    return "".join(res)


def tokenize(source: str) -> list[Token]:
    """
    Tokenizes a MicroScheme source string into a list of Tokens.
    Raises SchemeSyntaxError on malformed tokens, size overflow, or token cap exceeded.
    """
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise SchemeSyntaxError(f"Source size exceeds {MAX_SOURCE_BYTES} bytes limit.")

    tokens: list[Token] = []
    line_num = 1
    line_start = 0

    for match in TOKEN_REGEX.finditer(source):
        kind = match.lastgroup
        val = match.group()
        col = match.start() - line_start + 1

        if kind == "WS":
            if "\n" in val:
                line_num += val.count("\n")
                line_start = match.end() - len(val.split("\n")[-1])
            continue
        elif kind == "COMMENT":
            continue
        elif kind == "STRING":
            raw_inner = val[1:-1]
            processed = _unescape_scheme_string(raw_inner, line_num, col)
            tokens.append(Token("STRING", processed, line_num, col))
            if "\n" in val:
                line_num += val.count("\n")
                line_start = match.end() - len(val.split("\n")[-1])
        elif kind == "KEYWORD":
            tokens.append(Token("KEYWORD", val, line_num, col))
        elif kind == "FLOAT":
            tokens.append(Token("NUMBER", float(val), line_num, col))
        elif kind == "INT":
            tokens.append(Token("NUMBER", int(val), line_num, col))
        elif kind == "BOOLEAN":
            tokens.append(Token("BOOLEAN", val == "#t", line_num, col))
        elif kind == "LPAREN":
            tokens.append(Token("LPAREN", "(", line_num, col))
        elif kind == "RPAREN":
            tokens.append(Token("RPAREN", ")", line_num, col))
        elif kind == "SYMBOL":
            tokens.append(Token("SYMBOL", val, line_num, col))
        elif kind == "MISMATCH":
            raise SchemeSyntaxError(f"Unexpected character '{val}'", line_num, col)

        if len(tokens) > MAX_TOKENS:
            raise SchemeSyntaxError(
                f"Token count exceeds maximum limit of {MAX_TOKENS} tokens.", line_num, col
            )

    return tokens
