from typing import Any, Optional


class AppException(Exception):
    """
    Base exception class for all custom Regal Fitness application errors.
    """

    def __init__(
        self,
        detail: str = "An unexpected error occurred",
        status_code: int = 500,
        error_code: str = "INTERNAL_SERVER_ERROR",
        extra: Optional[Any] = None,
    ) -> None:
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code
        self.extra = extra
        super().__init__(detail)


class ResourceNotFoundException(AppException):
    def __init__(
        self,
        resource: str = "Resource",
        identifier: Optional[Any] = None,
        detail: Optional[str] = None,
    ) -> None:
        msg = detail or f"{resource} not found"
        if identifier is not None and not detail:
            msg = f"{resource} with identifier '{identifier}' not found"
        super().__init__(
            detail=msg,
            status_code=404,
            error_code="RESOURCE_NOT_FOUND",
        )


class ConflictException(AppException):
    def __init__(
        self,
        detail: str = "Resource conflict detected",
        extra: Optional[Any] = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=409,
            error_code="RESOURCE_CONFLICT",
            extra=extra,
        )


class BadRequestException(AppException):
    def __init__(
        self,
        detail: str = "Invalid request payload or parameters",
        extra: Optional[Any] = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=400,
            error_code="BAD_REQUEST",
            extra=extra,
        )


class DatabaseConnectionException(AppException):
    def __init__(
        self,
        detail: str = "Database service is unreachable",
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=503,
            error_code="DATABASE_UNAVAILABLE",
        )


class UnauthorizedException(AppException):
    def __init__(
        self,
        detail: str = "Authentication credentials are required or invalid",
        extra: Optional[Any] = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=401,
            error_code="UNAUTHORIZED",
            extra=extra,
        )


class ForbiddenException(AppException):
    def __init__(
        self,
        detail: str = "Access forbidden",
        extra: Optional[Any] = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=403,
            error_code="FORBIDDEN",
            extra=extra,
        )


class RateLimitExceededException(AppException):
    def __init__(
        self,
        detail: str = "Too many requests. Please try again later.",
        retry_after: Optional[int] = None,
    ) -> None:
        extra = {"retry_after_seconds": retry_after} if retry_after else None
        super().__init__(
            detail=detail,
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            extra=extra,
        )
