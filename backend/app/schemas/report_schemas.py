"""
Request/response schema cho FR-04.
  - EP-06 (T-034): CreateReportRequest / CreateReportResponse
  - EP-09 (T-035): ReportItemOut / ListMyReportsResponse
"""
from pydantic import BaseModel


class CreateReportRequest(BaseModel):
    # Cho phép thiếu/None để validate_and_normalize_entity() (T-030) quyết định
    # trả EMPTY_VALUE / INVALID_ENTITY đúng EX-04-2/EX-04-3, thay vì Pydantic
    # trả VALIDATION_ERROR chung khi client bỏ sót field.
    entity_type: str | None = None        # URL | PHONE | BANK_ACCOUNT | DOMAIN
    normalized_value: str | None = None   # giá trị thô người dùng nhập, server tự chuẩn hóa lại
    description: str | None = None


class CreateReportResponse(BaseModel):
    report_id: str
    status: str
    message: str


class ReportItemOut(BaseModel):
    """1 dòng trong 'Báo cáo của tôi' (L3.4 EP-09). KHÔNG có user_id (FR-04.8)."""
    report_id: str
    entity_type: str
    normalized_value: str
    status: str
    created_at: str


class ListMyReportsResponse(BaseModel):
    """Đúng L3.4 EP-09: chỉ có items + next_cursor, không thêm field khác."""
    items: list[ReportItemOut]
    next_cursor: str | None = None