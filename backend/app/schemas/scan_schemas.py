from typing import Optional, List, Any
from pydantic import BaseModel, Field


class CreateScanRequest(BaseModel):
    input_type: str = Field(..., pattern="^(TEXT|URL|PHONE|IMAGE)$", description="Loại đầu vào: TEXT / URL / PHONE / IMAGE")
    raw_content: str = Field(..., min_length=1, max_length=5000, description="Nội dung cần quét (text hoặc URL hoặc số điện thoại)")
    platform: Optional[str] = Field("web", max_length=20, description="Nền tảng thiết bị: web / android / ios")


class ScanEntityOut(BaseModel):
    entity_type: Optional[str] = None
    raw_value: Optional[str] = None
    normalized_value: Optional[str] = None


class ScanReasonOut(BaseModel):
    source: Optional[str] = None
    text: str = ""
    rule_code: Optional[str] = None
    score: int = 0
    evidence: Any = None


class CreateScanResponse(BaseModel):
    scan_id: str
    status: str
    input_type: str
    raw_content: str
    normalized_text: str
    risk_level: str
    final_score: int
    rule_score: int
    ai_score: Optional[int] = None
    ai_available: bool
    has_hard_override: bool
    entities: List[ScanEntityOut]
    reasons: List[ScanReasonOut]
    recommended_action: str
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
