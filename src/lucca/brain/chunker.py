"""
Project Lucca — Streaming Text Chunker & Normaliser
Spec 08 §3, §4, §5
"""

import re
import unicodedata
from typing import Final

from lucca.core.schemas import TTSChunk

ABBREVIATIONS: Final[frozenset[str]] = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "vs",
        "etc",
        "e.g",
        "i.e",
        "no",
        "approx",
        "dept",
        "est",
        "fig",
        "inc",
        "ltd",
        "co",
        "corp",
        "u.s",
        "u.k",
        "a.m",
        "p.m",
    }
)

FIRST_CHUNK_MIN_CHARS: Final = 24
FIRST_CHUNK_MAX_CHARS: Final = 90
MIN_CHARS: Final = 40
MAX_CHARS: Final = 220
FORCE_SPLIT_AT: Final = 260

URL_REGEX = re.compile(r"https?://[^\s<>\"'()]+")
MARKDOWN_LINK_REGEX = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
MARKDOWN_EMPHASIS_REGEX = re.compile(r"(\*\*|\*|__|_|`)(.*?)\1")
BULLET_REGEX = re.compile(r"^\s*(?:[-*]|\d+\.)\s+", re.MULTILINE)
HEADING_REGEX = re.compile(r"^\s*#+\s+", re.MULTILINE)


def normalise_text(text: str, speak_urls: bool = False) -> str:
    """Normalises text for TTS prosody and removes markdown/emojis per Spec 08 §3."""
    # 1. Smart quotes, dashes, ellipses
    s = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("…", "...").replace("—", ", ").replace("–", ", ")

    # 2. Markdown links [text](url) -> text
    s = MARKDOWN_LINK_REGEX.sub(r"\1", s)

    # 3. Bare URLs -> "a link"
    if not speak_urls:
        s = URL_REGEX.sub("a link", s)

    # 4. Markdown emphasis **x**, *x*, `x` -> x
    # Repeat to catch nested
    for _ in range(2):
        s = MARKDOWN_EMPHASIS_REGEX.sub(r"\2", s)

    # 5. Headings and list bullets at line starts
    s = HEADING_REGEX.sub("", s)
    s = BULLET_REGEX.sub("", s)

    # 6. Emoji / pictographs removal (Unicode categories So, Sk)
    cleaned_chars: list[str] = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat in ("So", "Sk") and ord(ch) > 127:
            continue
        cleaned_chars.append(ch)
    s = "".join(cleaned_chars)

    # 7. Multiple spaces/newlines -> single space; space before punctuation
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" ([,\.\?!;:])", r"\1", s)

    return s


class StreamingChunker:
    """
    Streaming sentence boundary detector and chunker for TTS synthesis.
    Thread-confined, stateful across a turn, resettable on barge-in.
    """

    def __init__(self, trace_id: str = "trace-0", speak_urls: bool = False) -> None:
        self.trace_id = trace_id
        self.speak_urls = speak_urls
        self.buffer = ""
        self.chunk_id = 0
        self.is_first = True
        self._spoken_chunks: list[str] = []
        self._paren_depth = 0

    @property
    def spoken_prefix(self) -> str:
        return " ".join(self._spoken_chunks)

    def reset(self) -> None:
        """Called on barge-in to cancel pending chunks and reset stream state."""
        self.buffer = ""
        self.chunk_id = 0
        self.is_first = True
        self._spoken_chunks.clear()
        self._paren_depth = 0

    def feed(self, delta: str) -> list[TTSChunk]:
        norm = normalise_text(delta, speak_urls=self.speak_urls)
        self.buffer += norm
        return self._extract_chunks(is_final=False)

    def flush(self) -> list[TTSChunk]:
        """Emits remaining buffer at end-of-stream."""
        return self._extract_chunks(is_final=True)

    def _extract_chunks(self, is_final: bool) -> list[TTSChunk]:
        emitted: list[TTSChunk] = []

        while self.buffer:
            target_min = FIRST_CHUNK_MIN_CHARS if self.is_first else MIN_CHARS
            target_max = FIRST_CHUNK_MAX_CHARS if self.is_first else MAX_CHARS

            split_pos = self._find_boundary(target_min, target_max, is_final)
            if split_pos is None:
                # Check run-on sentence force split
                if len(self.buffer) >= FORCE_SPLIT_AT:
                    # Split at last whitespace before or at FORCE_SPLIT_AT
                    last_ws = self.buffer.rfind(" ", 0, FORCE_SPLIT_AT)
                    if last_ws != -1:
                        split_pos = last_ws + 1
                    else:
                        split_pos = FORCE_SPLIT_AT
                elif is_final and self.buffer.strip():
                    split_pos = len(self.buffer)
                else:
                    break

            chunk_text = self.buffer[:split_pos].strip()
            self.buffer = self.buffer[split_pos:].lstrip()

            if chunk_text:
                chunk = TTSChunk(
                    trace_id=self.trace_id,
                    chunk_id=self.chunk_id,
                    text=chunk_text,
                    is_first=self.is_first,
                )
                self.chunk_id += 1
                self.is_first = False
                self._spoken_chunks.append(chunk_text)
                emitted.append(chunk)

        return emitted

    def _find_boundary(self, min_len: int, max_len: int, is_final: bool) -> int | None:
        buf = self.buffer
        n = len(buf)

        candidate_split: int | None = None

        for i in range(n):
            ch = buf[i]

            # Track quotes/parens
            if ch in ('"', "(", "["):
                self._paren_depth += 1
                if self._paren_depth > 3:
                    self._paren_depth = 0  # reset on malformed
            elif ch in ('"', ")", "]"):
                self._paren_depth = max(0, self._paren_depth - 1)

            if self._paren_depth > 0:
                continue

            # Punctuation check
            is_punct = ch in (".", "!", "?", ";", ":")
            is_soft = ch == "," and i >= min_len

            if not (is_punct or is_soft):
                continue

            # Lookahead check: confirmed only when next char is whitespace or end-of-stream
            if i + 1 < n:
                nxt = buf[i + 1]
                if not nxt.isspace():
                    continue
            elif not is_final:
                # Need one-token lookahead to confirm
                continue

            # Check for ellipsis: "..."
            if ch == "." and i >= 2 and buf[i - 2 : i + 1] == "...":
                # Ellipsis confirmed only if followed by space + uppercase
                if i + 2 < n and buf[i + 1].isspace() and buf[i + 2].isupper():
                    pass
                elif not is_final:
                    continue

            # Check abbreviation: extract preceding word
            if ch == ".":
                prev_text = buf[:i].rstrip()
                last_word = prev_text.split()[-1].lower() if prev_text.split() else ""
                # Strip leading punctuation from word
                last_word = last_word.lstrip("([\"'")
                if last_word in ABBREVIATIONS:
                    continue
                # Single capital letter (e.g. "J.")
                if len(last_word) == 1 and last_word.isupper():
                    continue
                # Numbered list item check (e.g. "1.")
                if last_word.isdigit() and len(prev_text.split()) == 1:
                    continue

            # Length criteria
            split_candidate = i + 1
            if split_candidate >= min_len:
                if split_candidate <= max_len:
                    return split_candidate
                elif candidate_split is None:
                    candidate_split = split_candidate

        return candidate_split
