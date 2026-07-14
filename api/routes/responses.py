from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

def ok(message: str, data: Any = None) -> dict:
    return {
        "success": True,
        "message": message,
        "data": data,
    }


def error_response(status_code: int, message: str, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({
            "success": False,
            "message": message,
            "data": data,
        }),
    )


def error_from_exception(error: Exception, *, conflict_on_value_error: bool = False) -> JSONResponse:
    if isinstance(error, HTTPException):
        return error_response(error.status_code, str(error.detail))

    if isinstance(error, FileNotFoundError):
        return error_response(status.HTTP_404_NOT_FOUND, str(error))

    if isinstance(error, KeyError):
        return error_response(status.HTTP_404_NOT_FOUND, str(error))

    if isinstance(error, ValueError):
        status_code = status.HTTP_409_CONFLICT if conflict_on_value_error else status.HTTP_400_BAD_REQUEST
        return error_response(status_code, str(error))

    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(error))
