"""Application exception hierarchy for database, authentication, and service operations."""


class AurenError(Exception):
    """Base exception for all AUREN application errors."""
    pass


class DatabaseError(AurenError):
    """Base exception for database failures."""
    def __init__(self, message: str, technical_details: str = ""):
        super().__init__(message)
        self.technical_details = technical_details


class DatabaseAuthError(DatabaseError):
    """Raised when authentication or authorization to the database/PostgREST fails (HTTP 401/403)."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when the database service cannot be reached (network failure, timeout)."""
    pass


class DatabaseOperationError(DatabaseError):
    """Raised when a database query or mutation fails on the server (HTTP 5xx or syntax error)."""
    pass


class ConversationNotFoundError(DatabaseError):
    """Raised when a requested conversation does not exist or access is denied."""
    pass


class IdempotencyConflictError(DatabaseError):
    """Raised when an idempotency key is reused with conflicting request parameters."""
    pass


