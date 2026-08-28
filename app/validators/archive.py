"""Archive-specific exceptions shared by service/tests."""


class UnsafeArchiveError(ValueError):
    """Raised when a ZIP archive violates extraction safety rules."""
