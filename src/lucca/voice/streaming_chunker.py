"""
Project Lucca — Streaming Audio Clause/Sentence Chunker
Splits LLM streaming token flow into optimal prosodic synthesis chunks
to achieve sub-400ms Time-to-First-Audio.
"""

import re
from typing import Generator, List

class StreamingSentenceChunker:
    def __init__(self, min_first_chunk_tokens: int = 5):
        self._min_first_chunk_tokens = min_first_chunk_tokens
        self._buffer: List[str] = []
        self._is_first_chunk = True
        self._clause_terminators = re.compile(r"[,;:\.!\?]\s*$")
        self._sentence_terminators = re.compile(r"[\.!\?]\s*$")

    def process_token(self, token: str) -> Generator[str, None, None]:
        """
        Ingests a single streaming token from the LLM.
        Yields synthesized text clauses when boundary conditions are satisfied.
        """
        self._buffer.append(token)
        current_text = "".join(self._buffer)
        token_count = len(self._buffer)

        if self._is_first_chunk:
            # First Chunk: Fire aggressively at clause punctuation once token count >= threshold
            if token_count >= self._min_first_chunk_tokens and self._clause_terminators.search(current_text):
                self._is_first_chunk = False
                self._buffer = []
                yield current_text.strip()
        else:
            # Subsequent Chunks: Fire strictly at sentence boundaries for natural prosody
            if self._sentence_terminators.search(current_text):
                self._buffer = []
                yield current_text.strip()

    def flush(self) -> Generator[str, None, None]:
        """Flushes any remaining text tokens at end of LLM stream."""
        if self._buffer:
            remaining = "".join(self._buffer).strip()
            self._buffer = []
            if remaining:
                yield remaining
        self._is_first_chunk = True
