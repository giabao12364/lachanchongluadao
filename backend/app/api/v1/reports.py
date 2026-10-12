"""
FR-04 — Báo cáo lừa đảo lên cộng đồng
  EP-06: POST /reports (T-034)
  EP-09: GET  /reports (T-035) — Báo cáo của tôi
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.v1.scans import decode_cursor, encode_cursor  
from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.core.rate_limit import check_report_rate_limit
from app.models.db_models import ScamReport
from app.schemas.report_schemas import (
    CreateReportRequest,
    CreateReportResponse,
    ListMyReportsResponse,
    ReportItemOut,
)
from app.services.reports.report_service import create_report
from app.services.reports.report_validator import (
    InvalidEntityError,
    validate_and_normalize_entity,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_TAG_FR04 = "FR-04: Báo cáo lừa đảo lên cộng đồng (EP-06 POST /reports, EP-09 GET /reports)"


def _ep06_error(code: str, message: str, status_code: int, extra: dict | None = None) -> HTTPException:
    """
    Theo convention chung (_ep01_error, _ep04_error): raise HTTPException với
    detail là dict. Handler toàn cục (app/core/exceptions.py, T-006) sẽ làm
    phẳng thành {code, message, extra} đúng L3.4 (extra tự thành null nếu vắng).
    Dùng chung cho cả EP-06 và EP-09 (cùng FR-04).
    """
    detail = {"code": code, "message": message}
    if extra is not None:
        detail["extra"] = extra
    return HTTPException(status_code=status_code, detail=detail)


def _iso_z(dt: datetime) -> str:
    """ISO-8601 UTC kết thúc bằng 'Z' (khớp ví dụ trong L3.4). Chịu được cả
    datetime naive (coi là UTC) lẫn aware, tránh sinh chuỗi '+00:00Z' sai."""
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@router.post(
    "/reports",
    response_model=CreateReportResponse,
    summary="[EP-06 / FR-04] Gửi báo cáo lừa đảo",
    tags=[_TAG_FR04],
)
def submit_report(
    body: CreateReportRequest,
    request: Request,
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị"),
    db: Session = Depends(get_db),
):
    """
    FR-04: User đã đăng nhập báo cáo 1 SĐT/link/số tài khoản/domain nghi
    lừa đảo -> validate & chuẩn hóa (BR-04-4, T-030) -> rate limit
    (BR-04-3, T-033) -> ghi nhận + auto-active blacklist nếu đủ ngưỡng
    (BR-04-1/BR-04-2, T-032).

    Route khai `def` (sync), KHÔNG `async def` — check_report_rate_limit()
    là hàm blocking (Redis + DB đồng bộ), không tự bọc run_in_threadpool.

    Errors:
        401 UNAUTHORIZED        — chưa đăng nhập (EX-04-1)
        422 INVALID_ENTITY      — entity_type/giá trị sai (EX-04-2)
        422 EMPTY_VALUE         — giá trị rỗng/thiếu (EX-04-3)
        429 REPORT_RATE_LIMITED — vượt 5 report/giờ/user (EX-04-5)
        500 INTERNAL_ERROR      — DB lỗi khi ghi (EX-04-6), không trả nửa vời
    """
    # EX-04-1: chưa đăng nhập
    user_id = get_current_user_id(request)
    if user_id is None:
        raise _ep06_error(
            "UNAUTHORIZED", "Vui lòng đăng nhập để gửi báo cáo",
            status.HTTP_401_UNAUTHORIZED,
        )

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

    try:
        result = create_report(db, user_id, entity, body.description)
    except Exception:
        logger.error("[submit_report][INFRA] create_report failed", exc_info=True)
        raise _ep06_error(
            "INTERNAL_ERROR", "Hệ thống đang gặp sự cố. Vui lòng thử lại.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

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


@router.get(
    "/reports",
    response_model=ListMyReportsResponse,
    summary="[EP-09 / FR-04] Báo cáo của tôi",
    tags=[_TAG_FR04],
)
def list_my_reports(
    request: Request,
    limit: int = Query(20, ge=1, le=50, description="Số dòng / trang (mặc định 20, tối đa 50)"),
    cursor: str | None = Query(None, description="Token next_cursor của trang trước"),
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị"),
    db: Session = Depends(get_db),
):
    """
    FR-04.7 / EP-09: danh sách report của CHÍNH user đang đăng nhập, sắp
    created_at DESC, phân trang cursor (created_at + id).

    - Lọc cứng theo user_id lấy từ token -> không có cách nào thấy report của
      người khác (AT-04-7). Không có tham số nào cho phép chỉ định user khác.
    - Response KHÔNG chứa user_id (FR-04.8) và không có field ngoài L3.4.
    - Chỉ đọc (BR-04-5: không có sửa/xóa report).

    Errors:
        401 UNAUTHORIZED — chưa đăng nhập
    Cursor sai định dạng -> tự tải lại từ trang đầu (EX-06-4 cho phép).
    """
    user_id = get_current_user_id(request)
    if user_id is None:
        raise _ep06_error(
            "UNAUTHORIZED", "Vui lòng đăng nhập để xem báo cáo của bạn",
            status.HTTP_401_UNAUTHORIZED,
        )

    query = db.query(ScamReport).filter(ScamReport.user_id == user_id)

    if cursor:
        try:
            cursor_created_at, cursor_id = decode_cursor(cursor)
            query = query.filter(
                (ScamReport.created_at < cursor_created_at)
                | ((ScamReport.created_at == cursor_created_at) & (ScamReport.id < cursor_id))
            )
        except Exception:
            pass  # cursor hỏng -> bỏ qua, trả từ trang đầu

    rows = (
        query
        .order_by(ScamReport.created_at.desc(), ScamReport.id.desc())
        .limit(limit + 1)
        .all()
    )

    has_next = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_next and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    items = [
        ReportItemOut(
            report_id=str(r.id),
            entity_type=r.entity_type.value,
            normalized_value=r.normalized_value,
            status=r.status.value,
            created_at=_iso_z(r.created_at),
        )
        for r in rows
    ]

    return ListMyReportsResponse(items=items, next_cursor=next_cursor).model_dump()