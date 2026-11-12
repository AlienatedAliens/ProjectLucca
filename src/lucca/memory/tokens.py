"""
Project Lucca — Memory Token & Query Processing
Spec 04 §2, §6, Property Test P-06
"""

import base64
import hashlib
import hmac
import re
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from lucca.core.schemas import Provenance

SPLIT_PATTERN: Final[re.Pattern[str]] = re.compile(r"[_.\-/\\]+")
ED25519_SIG_PREFIX: Final[str] = "ed25519:"


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if not salt:
        salt = b"\x00" * 32
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int = 32) -> bytes:
    t = b""
    okm = b""
    i = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


def derive_provenance_key(master_key: bytes, provenance: Provenance) -> bytes:
    """HKDF(SHA256, ikm=master, salt=b'lucca-v2', info=b'prov/' + provenance.value, L=32)."""
    prk = hkdf_extract(salt=b"lucca-v2", ikm=master_key)
    info = b"prov/" + provenance.value.encode("utf-8")
    return hkdf_expand(prk, info=info, length=32)


def derive_ed25519_private_key(master_key: bytes, provenance: Provenance) -> Ed25519PrivateKey:
    """Derives an RFC 8032 Ed25519 private key per provenance via domain-separated HKDF-SHA256."""
    prk = hkdf_extract(salt=b"lucca-ed25519-v1", ikm=master_key)
    info = b"ed25519/prov/" + provenance.value.encode("utf-8")
    seed = hkdf_expand(prk, info=info, length=32)
    return Ed25519PrivateKey.from_private_bytes(seed)


def derive_ed25519_public_key(master_key: bytes, provenance: Provenance) -> Ed25519PublicKey:
    """Derives the corresponding RFC 8032 Ed25519 public key for a provenance domain."""
    return derive_ed25519_private_key(master_key, provenance).public_key()


def derive_ed25519_public_keys(master_key: bytes) -> dict[Provenance, Ed25519PublicKey]:
    """Derives the complete provenance -> Ed25519PublicKey verification map."""
    return {p: derive_ed25519_public_key(master_key, p) for p in Provenance}


def sign_ed25519_canonical(private_key: Ed25519PrivateKey, canonical_bytes: bytes) -> str:
    """Produces a prefixed base64 RFC 8032 Ed25519 signature over canonical payload bytes."""
    raw_sig = private_key.sign(canonical_bytes)
    return ED25519_SIG_PREFIX + base64.b64encode(raw_sig).decode("ascii")


def verify_provenance_signature(
    signature: str,
    canonical_bytes: bytes,
    provenance: Provenance,
    *,
    public_key: Ed25519PublicKey | None = None,
    master_key: bytes | None = None,
    allow_legacy_hmac: bool = True,
) -> bool:
    """
    Verifies an asymmetric Ed25519 signature (`ed25519:<base64>`), with optional
    read-only backwards compatibility for pre-v1.52 unprefixed HMAC-SHA256 rows.
    Never downgrades an `ed25519:` signature to HMAC.
    """
    if signature.startswith(ED25519_SIG_PREFIX):
        pub = public_key or (
            derive_ed25519_public_key(master_key, provenance) if master_key is not None else None
        )
        if pub is None:
            return False
        b64_part = signature[len(ED25519_SIG_PREFIX) :]
        try:
            raw_sig = base64.b64decode(b64_part, validate=True)
        except ValueError:
            return False
        if len(raw_sig) != 64:
            return False
        try:
            pub.verify(raw_sig, canonical_bytes)
            return True
        except InvalidSignature:
            return False

    if not allow_legacy_hmac or master_key is None:
        return False

    legacy_key = derive_provenance_key(master_key, provenance)
    expected_raw = hmac.new(legacy_key, canonical_bytes, hashlib.sha256).digest()
    expected_sig = base64.b64encode(expected_raw).decode("ascii")
    return hmac.compare_digest(signature, expected_sig)


def subtokens(text: str) -> str:
    """
    Extract auxiliary sub-tokens by splitting tokens on delimiters (_ . - / \\).
    A pure Python function used identically at index time (before INSERT)
    and at query time.
    """
    cleaned = text.replace("\x00", " ")
    parts: list[str] = []
    for word in cleaned.split():
        sub_parts = SPLIT_PATTERN.split(word)
        if len(sub_parts) > 1:
            for p in sub_parts:
                p_clean = p.strip()
                if p_clean:
                    parts.append(p_clean)
    return " ".join(parts)


STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "ought",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }
)


def clean_term(token: str) -> str:
    """Strip edge punctuation while preserving inner delimiters."""
    return token.strip(" \t\r\n.,!?:;\"'()[]{}<>~`#$*")


def escape_fts_token(token: str) -> str:
    """
    Escape an individual token for safe use in FTS5 MATCH queries.
    Strips internal null bytes, trims, and doubles any double-quotes.
    """
    cleaned = token.replace("\x00", " ").strip()
    if not cleaned:
        return '""'
    escaped = cleaned.replace('"', '""')
    return f'"{escaped}"'


def build_fts_query(text: str) -> str:
    """
    Construct a valid, injection-safe FTS5 MATCH expression from arbitrary text.
    Filters out conversational stop words when informative content tokens exist,
    strips edge punctuation, and wraps each token in double quotes with quote-doubling.
    Guarantees that ANY input string executes without error against FTS5 tables (P-06).
    """
    sanitized = text.replace("\x00", " ")
    raw_tokens = sanitized.split()
    if not raw_tokens:
        return '""'

    cleaned = [clean_term(t) for t in raw_tokens]
    valid_tokens = [t for t in cleaned if t]
    if not valid_tokens:
        return '""'

    content_tokens = [t for t in valid_tokens if t.lower() not in STOP_WORDS]
    tokens_to_use = content_tokens if content_tokens else valid_tokens

    escaped_tokens = [escape_fts_token(t) for t in tokens_to_use if t.strip()]
    return " OR ".join(escaped_tokens) if escaped_tokens else '""'
