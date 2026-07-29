"""API cung cấp catalog model được khám phá từ thư mục weights."""

from typing import Literal

from fastapi import APIRouter, Query

from api.models.response import ApiResponse
from api.routes.responses import error_from_exception, ok
from src.model_catalog import list_models


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
@router.get("", response_model=ApiResponse)
def get_models(
    kind: Literal["detection", "reid"] | None = Query(default=None),
):
    """Quét lại thư mục weights và trả danh sách model khả dụng."""
    try:
        models = [model.to_dict() for model in list_models(kind)]
        return ok("Model catalog loaded successfully.", models)
    except Exception as error:
        return error_from_exception(error)
