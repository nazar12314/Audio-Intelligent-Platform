from typing import Any


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "Internal server error"

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code, code, default_message = 404, "not_found", "Resource not found"

    def __init__(self, resource: str, resource_id: object) -> None:
        super().__init__(
            f"{resource} {resource_id} not found",
            details={"resource": resource, "id": str(resource_id)},
        )


class ConflictError(AppError):
    status_code, code, default_message = (
        409,
        "conflict",
        "Conflict with the current state of the resource",
    )


class ValidationFailed(AppError):
    status_code, code, default_message = (
        422,
        "validation_failed",
        "Request validation failed",
    )


class Unauthorized(AppError):
    status_code, code, default_message = 401, "unauthorized", "Authentication required"


class Forbidden(AppError):
    status_code, code, default_message = 403, "forbidden", "Not allowed"


class RateLimited(AppError):
    status_code, code, default_message = 429, "rate_limited", "Too many requests"


class DependencyUnavailable(AppError):
    status_code, code, default_message = (
        503,
        "dependency_unavailable",
        "A required dependency is unavailable",
    )
