"""
Direct unit tests for MicroScheme v2 Lexer.
lucca.reasoning.scheme.lexer
Spec 05 §2, §3
"""

import pytest

from lucca.core.exceptions import SchemeSyntaxError
from lucca.reasoning.scheme.lexer import (
    MAX_SOURCE_BYTES,
    MAX_TOKENS,
    Token,
    _unescape_scheme_string,
    tokenize,
)


def test_token_dataclass() -> None:
    """Token dataclass is frozen and provides correct fields."""
    tok = Token("KEYWORD", ":when", 1, 3)
    assert tok.type == "KEYWORD"
    assert tok.value == ":when"
    assert tok.line == 1
    assert tok.col == 3

    with pytest.raises(Exception):  # FrozenInstanceError
        tok.value = ":plan"  # type: ignore[misc]


def test_tokenize_all_token_types() -> None:
    """All MicroScheme token types tokenize into expected Token objects."""
    source = '(rule :when #t #f 42 -7 3.14 -0.5 "hello \\"world\\"" + <= my-symbol ; comment\n)'
    tokens = tokenize(source)

    expected = [
        ("LPAREN", "(", 1, 1),
        ("SYMBOL", "rule", 1, 2),
        ("KEYWORD", ":when", 1, 7),
        ("BOOLEAN", True, 1, 13),
        ("BOOLEAN", False, 1, 16),
        ("NUMBER", 42, 1, 19),
        ("NUMBER", -7, 1, 22),
        ("NUMBER", 3.14, 1, 25),
        ("NUMBER", -0.5, 1, 30),
        ("STRING", 'hello "world"', 1, 35),
        ("SYMBOL", "+", 1, 53),
        ("SYMBOL", "<=", 1, 55),
        ("SYMBOL", "my-symbol", 1, 58),
        ("RPAREN", ")", 2, 1),
    ]

    assert len(tokens) == len(expected)
    for tok, (exp_type, exp_val, exp_line, exp_col) in zip(tokens, expected, strict=True):
        assert tok.type == exp_type
        assert tok.value == exp_val
        assert tok.line == exp_line
        assert tok.col == exp_col


def test_tokenize_empty_and_whitespace_only() -> None:
    """Empty or comment-only sources return empty token list."""
    assert tokenize("") == []
    assert tokenize("   \n\t   \n") == []
    assert tokenize("; just a comment\n; another comment\n") == []


def test_tokenize_string_escape_sequences() -> None:
    """Supported string escape sequences (\\", \\\\, \\n, \\t) are correctly unescaped."""
    src = r'"quote: \" backslash: \\ newline: \n tab: \t"'
    tokens = tokenize(src)
    assert len(tokens) == 1
    assert tokens[0].type == "STRING"
    assert tokens[0].value == 'quote: " backslash: \\ newline: \n tab: \t'


def test_unescape_scheme_string_direct() -> None:
    """Direct tests for _unescape_scheme_string helper."""
    assert _unescape_scheme_string(r'abc\"def', 1, 1) == 'abc"def'
    assert _unescape_scheme_string(r"abc\\def", 1, 1) == "abc\\def"
    assert _unescape_scheme_string(r"abc\ndef", 1, 1) == "abc\ndef"
    assert _unescape_scheme_string(r"abc\tdef", 1, 1) == "abc\tdef"

    with pytest.raises(SchemeSyntaxError, match="Trailing backslash"):
        _unescape_scheme_string("abc\\", 2, 5)

    with pytest.raises(SchemeSyntaxError, match=r"Invalid escape sequence \\x"):
        _unescape_scheme_string(r"abc\xdef", 2, 5)


def test_tokenize_multiline_line_col_tracking() -> None:
    """Line and column tracking correctly tracks across newlines and tokens."""
    source = "(+\n  10\n  20)"
    tokens = tokenize(source)
    assert tokens[0] == Token("LPAREN", "(", 1, 1)
    assert tokens[1] == Token("SYMBOL", "+", 1, 2)
    assert tokens[2] == Token("NUMBER", 10, 2, 3)
    assert tokens[3] == Token("NUMBER", 20, 3, 3)
    assert tokens[4] == Token("RPAREN", ")", 3, 5)


def test_tokenize_multiline_string_line_tracking() -> None:
    """Multiline strings increment line counts properly."""
    source = '"line1\nline2\nline3"\n:done'
    tokens = tokenize(source)
    assert len(tokens) == 2
    assert tokens[0].type == "STRING"
    assert tokens[0].value == "line1\nline2\nline3"
    assert tokens[0].line == 1
    assert tokens[1].type == "KEYWORD"
    assert tokens[1].value == ":done"
    assert tokens[1].line == 4


def test_tokenize_max_source_bytes_exceeded() -> None:
    """Sources exceeding MAX_SOURCE_BYTES (8,192) raise SchemeSyntaxError."""
    # Exactly at limit should succeed
    exact_src = ";" + "a" * (MAX_SOURCE_BYTES - 1)
    assert len(exact_src.encode("utf-8")) == MAX_SOURCE_BYTES
    tokenize(exact_src)

    # Exceeding limit raises SchemeSyntaxError
    over_src = exact_src + "x"
    assert len(over_src.encode("utf-8")) > MAX_SOURCE_BYTES
    with pytest.raises(SchemeSyntaxError, match=f"Source size exceeds {MAX_SOURCE_BYTES} bytes limit."):
        tokenize(over_src)

    # Multi-byte UTF-8 characters count by byte length
    utf8_src = "€" * (MAX_SOURCE_BYTES // 3 + 1)
    assert len(utf8_src.encode("utf-8")) > MAX_SOURCE_BYTES
    with pytest.raises(SchemeSyntaxError, match=f"Source size exceeds {MAX_SOURCE_BYTES} bytes limit."):
        tokenize(utf8_src)


def test_tokenize_max_tokens_exceeded() -> None:
    """Sources producing more than MAX_TOKENS (2,000) raise SchemeSyntaxError."""
    # Exactly 2,000 tokens succeeds
    tokens_2000 = " ".join(["1"] * MAX_TOKENS)
    toks = tokenize(tokens_2000)
    assert len(toks) == MAX_TOKENS

    # 2,001 tokens raises SchemeSyntaxError
    tokens_2001 = " ".join(["1"] * (MAX_TOKENS + 1))
    with pytest.raises(
        SchemeSyntaxError, match=f"Token count exceeds maximum limit of {MAX_TOKENS} tokens."
    ):
        tokenize(tokens_2001)


def test_tokenize_invalid_character_mismatch() -> None:
    """Unexpected characters hit MISMATCH pattern and raise SchemeSyntaxError."""
    import re
    invalid_chars = ["@", "$", "%", "^", "~", "`"]
    for ch in invalid_chars:
        with pytest.raises(SchemeSyntaxError, match=f"Unexpected character '{re.escape(ch)}'") as exc:
            tokenize(f"(+ 1 {ch} 2)")
        assert exc.value.line == 1


def test_tokenize_boolean_lookahead_boundary() -> None:
    """#t and #f require negative lookahead to not match extended symbol-like text."""
    # '#t' followed by valid symbol char '#true' does not match boolean
    with pytest.raises(SchemeSyntaxError, match="Unexpected character '#'"):
        tokenize("#true")
