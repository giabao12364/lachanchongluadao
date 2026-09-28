import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.core.rate_limit import check_report_rate_limit
from app.schemas.report_schemas import CreateReportRequest, CreateReportResponse
from app.services.reports.report_service import create_report
from app.services.reports.report_validator import (
    InvalidEntityError,
    validate_and_normalize_entity,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_TAG_FR04 = "FR-04: Báo cáo lừa đảo lên cộng đồng (EP-06 POST /reports)"


def _ep06_error(code: str, message: str, status_code: int, extra: dict | None = None) -> HTTPException:
    detail = {"code": code, "message": message}
    if extra is not None:
        detail["extra"] = extra
    return HTTPException(status_code=status_code, detail=detail)


@router.post(
    "/reports",
    summary="[EP-06 / FR-04] Gửi báo cáo lừa đảo",
    tags=[_TAG_FR04],
)
def submit_report(
    body: CreateReportRequest,
    request: Request,
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị"),
    db: Session = Depends(get_db),
):
    # EX-04-1: chưa đăng nhập
    user_id = get_current_user_id(request)
    if user_id is None:
        raise _ep06_error(
            "UNAUTHORIZED", "Vui lòng đăng nhập để gửi báo cáo",
            status.HTTP_401_UNAUTHORIZED,
        )

    # BR-04-4 / EX-04-2 / EX-04-3: validate & chuẩn hóa (T-030)
    try:
        entity = validate_and_normalize_entity(body.entity_type, body.normalized_value)
    except InvalidEntityError as e:
        raise _ep06_error(e.code, e.message, status.HTTP_422_UNPROCESSABLE_ENTITY)

    # BR-04-3 / EX-04-5: rate limit
    retry_after = check_report_rate_limit(str(user_id))
    if retry_after is not None:
        raise _ep06_error(
            "REPORT_RATE_LIMITED",
            "Bạn đã gửi báo cáo quá nhiều lần. Vui lòng thử lại sau.",
            status.HTTP_429_TOO_MANY_REQUESTS,
            extra={"retry_after": retry_after},
        )

    # EX-04-6: DB lỗi -> 500, không trả kết quả nửa vời. create_report() đã
    # tự rollback trong transaction của nó (xem report_service.py).
    try:
        result = create_report(db, user_id, entity, body.description)
    except Exception:
        logger.error("[submit_report][INFRA] create_report failed", exc_info=True)
        raise _ep06_error(
            "INTERNAL_ERROR", "Hệ thống đang gặp sự cố. Vui lòng thử lại.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # EX-04-4: đã report rồi -> vẫn 200, đổi message, KHÔNG tạo bản ghi mới
    message = (
        "Bạn đã báo cáo mục này trước đó"
        if result.is_duplicate
        else "Đã ghi nhận báo cáo của bạn, cảm ơn bạn đã giúp cộng đồng"
    )

    return CreateReportResponse(
        report_id=str(result.report_id),
        status=result.status,
        message=message,
    ).model_dump()