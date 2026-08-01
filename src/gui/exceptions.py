"""Stable application exceptions for the desktop presentation layer."""


class GuiError(Exception):
    """Base exception for expected GUI-layer failures."""


class InvalidGenerationFormError(GuiError):
    """Raised when user-provided form values cannot create a valid request."""


class ApplicationExecutionError(GuiError):
    """Raised when the application facade cannot complete a GUI request."""
