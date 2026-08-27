"""Domain exceptions with safe, actionable messages."""


class AgEconLiteratureError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(AgEconLiteratureError):
    """Raised when a local configuration violates a safety constraint."""


class SetupRequired(AgEconLiteratureError):
    """Raised when a required interactive setup step has not been completed."""


class SourceUnavailable(AgEconLiteratureError):
    """Raised when an external source cannot currently be reached or parsed."""


class InvalidPlan(AgEconLiteratureError):
    """Raised when a plan is missing, expired, changed, or not confirmable."""


class ConflictDetected(AgEconLiteratureError):
    """Raised when an operation would require unsafe duplicate resolution."""


class PdfValidationError(AgEconLiteratureError):
    """Raised when a retrieved file is not a valid PDF."""


class ZoteroError(AgEconLiteratureError):
    """Raised for Zotero Local API protocol failures."""


class ZoteroAuthorizationRequired(ZoteroError):
    """Raised when a remembered Zotero Local API key is unavailable or invalid."""


class ZoteroServerChanged(ZoteroError):
    """Raised when a plan belongs to a different Zotero local database."""
