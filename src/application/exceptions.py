"""Stable exception types exposed by the application facade."""


class ApplicationError(Exception):
    """Base exception for expected application-level operation failures."""


class InvalidApplicationRequestError(ApplicationError):
    """Raised when the supplied application request is invalid."""


class ApplicationPipelineError(ApplicationError):
    """Raised when the delegated pipeline cannot complete successfully."""
