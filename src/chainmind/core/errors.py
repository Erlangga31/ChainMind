"""Expected domain and integration errors surfaced as structured API responses."""


class ChainMindError(Exception):
    """Base error carrying a stable public error code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class IntegrationError(ChainMindError):
    """Expected failure from an external integration."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            "integration_error",
            message,
            status_code=503,
            details=details,
        )
