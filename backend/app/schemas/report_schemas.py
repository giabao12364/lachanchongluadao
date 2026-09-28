from pydantic import BaseModel


class CreateReportRequest(BaseModel):
    entity_type: str | None = None        # URL | PHONE | BANK_ACCOUNT | DOMAIN
    normalized_value: str | None = None   # giá trị thô người dùng nhập, server tự chuẩn hóa lại
    description: str | None = None


class CreateReportResponse(BaseModel):
    report_id: str
    status: str
    message: str