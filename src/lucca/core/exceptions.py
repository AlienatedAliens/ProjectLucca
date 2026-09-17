"""
Project Lucca — Error Taxonomy
Spec 11 §3 (`lucca.core.exceptions`)
"""


class LuccaError(Exception):
    """Base exception for all Project Lucca system errors."""

    pass


class ConfigError(LuccaError):
    """Raised when configuration fails loading or validation."""

    pass


class BootError(LuccaError):
    """Raised when system supervisor or child processes fail during boot."""

    pass


class IPCError(LuccaError):
    """Raised on socket timeout, frame corruption, or connection drops."""

    pass


# LLM Errors
class LLMError(LuccaError):
    """Base exception for LLM provider errors."""

    pass


class LLMUnavailable(LLMError):
    """llama-server is not reachable or slots are exhausted."""

    pass


class LLMTimeout(LLMError):
    """LLM request timed out before first token or total duration."""

    pass


class LLMProtocolError(LLMError):
    """Malformed response, grammar violation, or unexpected HTTP payload."""

    pass


# ASR & TTS Errors
class ASRError(LuccaError):
    """Whisper transcription failure or device error."""

    pass


class TTSError(LuccaError):
    """Base exception for TTS failure."""

    pass


class TTSFailed(TTSError):
    """Kokoro synthesis failure on target device ladder."""

    pass


# Memory & Provenance Errors
class MemoryError_(LuccaError):
    """Base exception for memory storage failures."""

    pass


class MemoryCommitFailed(MemoryError_):
    """Failed to write transaction to SQLite store."""

    pass


class MemoryLocked(MemoryError_):
    """SQLite database is locked after retry attempts."""

    pass


class MemoryIntegrity(MemoryError_):
    """PRAGMA integrity_check failed or corrupt memory row detected."""

    pass


class ProvenanceRejected(MemoryError_):
    """Memory write attempt lacks valid provenance signer or is LLM_NARRATION."""

    pass


class GroundingError(MemoryError_):
    """USER_DERIVED memory extraction lacks verbatim quote grounding."""

    pass


# Scheme / Symbolic Reasoning Errors
class SchemeError(LuccaError):
    """Base exception for MicroScheme engine."""

    pass


class SchemeSyntaxError(SchemeError):
    """Malformed S-expression syntax."""

    def __init__(self, message: str, line: int | None = None, col: int | None = None) -> None:
        self.line = line
        self.col = col
        if line is not None and col is not None:
            super().__init__(f"{message} at line {line}, col {col}")
        else:
            super().__init__(message)


class SchemeRuntimeError(SchemeError):
    """Type error, unbound variable, or division by zero in S-expression."""

    def __init__(
        self,
        message: str,
        rule_id: str | None = None,
        form: str | None = None,
        cause_type: str | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.form = form
        self.cause_type = cause_type
        super().__init__(message)


class SchemeGasExhausted(SchemeError):
    """Execution step limit (gas) exceeded."""

    pass


class SchemeTimeout(SchemeError):
    """Evaluation duration exceeded per-rule timeout limit."""

    pass


# Rule Lifecycle Errors
class RuleError(LuccaError):
    """Base exception for rule promotion and management."""

    pass


class RuleConflict(RuleError):
    """Candidate rule conflicts with existing active rule invariant."""

    pass


class RuleValidationError(RuleError):
    """Candidate rule fails static AST validation or schema."""

    pass


# Sandbox Errors
class SandboxError(LuccaError):
    """Base exception for container sandbox execution."""

    pass


class SandboxPathError(SandboxError):
    """Attempted path traversal or escape from workspace boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


class SandboxTimeout(SandboxError):
    """Tool call execution timed out inside container."""

    pass


class SandboxProtocolError(SandboxError):
    """Malformed JSON-RPC response from sandbox tool."""

    pass


class SandboxEgressError(SandboxError):
    """Sandbox network egress rule violation detected."""

    pass


# Launcher Errors
class LauncherError(LuccaError):
    """Base exception for host-mediated application launcher."""

    pass


class LauncherNotWhitelisted(LauncherError):
    """Application identifier is not in the immutable whitelist."""

    pass


class LauncherRateLimited(LauncherError):
    """Too many application launch requests in time window."""

    pass


# Router Errors
class RouterError(LuccaError):
    """Base exception for routing subsystem."""

    pass


class RouterInsufficientCalibration(RouterError):
    """Trained router called before meeting minimum sample count data floor."""

    pass


InsufficientCalibration = RouterInsufficientCalibration
