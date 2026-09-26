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


# ASR & TTS Errors
class TTSError(LuccaError):
    """Base exception for TTS failure."""

    pass


# Memory & Provenance Errors
class MemoryError_(LuccaError):
    """Base exception for memory storage failures."""

    pass


class MemoryCommitFailed(MemoryError_):
    """Failed to write transaction to SQLite store."""

    pass


class MemoryStoreReadOnly(MemoryError_):
    """MemoryStore is in read-only mode (e.g. after integrity failure)."""

    pass


class ProvenanceRejected(MemoryError_):
    """Memory write attempt lacks valid provenance signer or is LLM_NARRATION."""

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


class SchemeControlSignal(LuccaError):
    """Base class for non-exceptional control-flow signals in MicroScheme."""

    pass


class SchemeYieldSignal(SchemeControlSignal):
    """Raised by (yield-to-core reason context) to yield S1 control to System 2."""

    def __init__(self, reason: str, context: dict[str, object] | None = None) -> None:
        self.reason = reason
        self.context: dict[str, object] = context or {}
        super().__init__(f"Yield to neural core: {reason}")


class SchemeInterruptSignal(SchemeControlSignal):
    """Raised by (interrupt-core reason) to abort the current turn out-of-band."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Interrupt neural core: {reason}")


# Rule Lifecycle Errors
class RuleError(LuccaError):
    """Base exception for rule promotion and management."""

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
        self.message = message
        super().__init__(f"[{code}] {message}")


class SandboxTimeout(SandboxError):
    """Tool call execution timed out inside container."""

    pass


class SandboxProtocolError(SandboxError):
    """Malformed JSON-RPC response from sandbox tool."""

    pass


class SandboxRPCDesyncError(SandboxProtocolError):
    """Call-ID desynchronization or corrupted response sequence in persistent RPC bridge."""

    pass


# Launcher Errors
class LauncherError(LuccaError):
    """Base exception for host-mediated application launcher."""

    pass


# Router Errors
class RouterError(LuccaError):
    """Base exception for routing subsystem."""

    pass


class RouterInsufficientCalibration(RouterError):
    """Trained router called before meeting minimum sample count data floor."""

    pass


InsufficientCalibration = RouterInsufficientCalibration
