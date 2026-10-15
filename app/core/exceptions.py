"""Application-specific exception types for SEC document extraction."""


class SecDocumentExtractorError(Exception):
    """Base exception for all domain-specific SEC extraction errors."""


class ConfigurationError(SecDocumentExtractorError):
    """Raised when runtime configuration is missing or invalid."""


class TickerResolutionError(SecDocumentExtractorError):
    """Raised when a ticker cannot be mapped to a valid SEC CIK."""


class SecApiResponseError(SecDocumentExtractorError):
    """Raised when the SEC responds with invalid, incomplete, or unexpected data."""

