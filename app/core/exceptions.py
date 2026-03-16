"""Custom exceptions for ComplianceAstra API."""
from fastapi import HTTPException


class AppException(HTTPException):
    """Base application exception with status code and detail."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


class NotFoundError(AppException):
    def __init__(self, resource: str, identifier: str | int):
        super().__init__(404, f"{resource} not found: {identifier}")


class ForbiddenError(AppException):
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(403, detail)


class ValidationError(AppException):
    def __init__(self, detail: str):
        super().__init__(400, detail)


class ClaimExpiredError(AppException):
    def __init__(self):
        super().__init__(400, "Claim token has expired")


class ClaimAlreadyUsedError(AppException):
    def __init__(self):
        super().__init__(400, "Assessment already claimed")
