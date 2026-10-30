"""Errors the service layer raises. The agent tools turn these into JSON the model can read."""


class DomainError(Exception):
    code = "error"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}  # structured facts the agent can use (e.g. the existing student)


class AuthenticationFailed(DomainError):
    """Not logged in, or bad credentials. (PermissionDenied = logged in but not allowed.)"""

    code = "authentication_failed"


class PermissionDenied(DomainError):
    code = "permission_denied"


class NotFound(DomainError):
    code = "not_found"


class InvalidRequest(DomainError):
    code = "invalid_request"


class Conflict(DomainError):
    """The request is valid but clashes with current data (already exists, already done...)."""

    code = "conflict"
