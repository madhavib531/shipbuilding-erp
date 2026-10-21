"""Custom exception handling."""

from fastapi import HTTPException, status


class ItemNotFoundError(HTTPException):
    """Raised when a requested item is not found."""
    def __init__(self, item_type: str, item_id):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{item_type} with id {item_id} not found"
        )


class InvalidInputError(HTTPException):
    """Raised when input validation fails."""
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=message
        )


class ConflictError(HTTPException):
    """Raised when a resource conflict occurs."""
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=message
        )


class InternalServerError(HTTPException):
    """Raised for unexpected server errors."""
    def __init__(self, message: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message
        )
