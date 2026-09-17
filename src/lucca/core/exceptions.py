"""
Project Lucca — Custom Exception Hierarchy
"""

class LuccaException(Exception):
    """Base exception for all Lucca system errors."""
    pass

class SecurityException(LuccaException):
    """Raised when an action violates security or sandboxing boundaries."""
    pass

class ProvenanceViolationException(SecurityException):
    """Raised when an unverified narration attempts to write to long-term memory."""
    pass

class PathTraversalException(SecurityException):
    """Raised when a file path escapes the sandbox root."""
    pass

class GasExhaustedException(LuccaException):
    """Raised when a LISP execution exceeds its allocated computational fuel."""
    pass

class HardwareBudgetException(LuccaException):
    """Raised when memory or compute exceeds configured physical ceilings."""
    pass

class PromotionGateException(LuccaException):
    """Raised when a candidate rule fails promotion criteria."""
    pass
