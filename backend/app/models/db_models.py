import uuid
import enum

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    ForeignKey,
    TIMESTAMP,
    CheckConstraint,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum

from app.core.database import Base


# =========================================================
# ENUM — nguyên văn theo L0.5 Glossary & Enum đóng kín
# Thêm giá trị mới PHẢI sửa L0.5 trong tài liệu trước, rồi mới sửa ở đây.
# =========================================================

class RiskLevel(str, enum.Enum):
    AN_TOAN = "AN_TOAN"
    NGHI_NGO = "NGHI_NGO"
    NGUY_HIEM = "NGUY_HIEM"


class InputType(str, enum.Enum):
    TEXT = "TEXT"
    URL = "URL"
    PHONE = "PHONE"
    IMAGE = "IMAGE"


class ScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SignalSource(str, enum.Enum):
    BLACKLIST = "BLACKLIST"
    RULE = "RULE"
    AI = "AI"
    COMMUNITY = "COMMUNITY"


class EntityType(str, enum.Enum):
    URL = "URL"
    PHONE = "PHONE"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    DOMAIN = "DOMAIN"


class BlacklistSource(str, enum.Enum):
    COMMUNITY = "COMMUNITY"
    PUBLIC_FEED = "PUBLIC_FEED"
    MANUAL = "MANUAL"


class ReportStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# =========================================================
# TABLE: app_user  — Tài khoản đã đăng ký (FR-05)
# NOTE: phone_number đang giả định SĐT — xem Mục treo #3 (PL.3), CHƯA CHỐT
# =========================================================
class AppUser(Base):
    __tablename__ = "app_user"

    id = uuid_pk()
    phone_number = Column(String(20), unique=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# =========================================================
# TABLE: device — Định danh người dùng ẩn danh
# =========================================================
class Device(Base):
    __tablename__ = "device"

    id = uuid_pk()
    device_uid = Column(String(128), unique=True, nullable=False)
    platform = Column(String(20), nullable=False)  # ios | android
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("device_uid", name="uq_device_device_uid"),
    )


# =========================================================
# TABLE: scan_request — Mỗi lượt quét (FR-01)
# =========================================================
class ScanRequest(Base):
    __tablename__ = "scan_request"

    id = uuid_pk()
    device_id = Column(UUID(as_uuid=True), ForeignKey("device.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True)
    input_type = Column(SAEnum(InputType, name="input_type"), nullable=False)
    raw_content = Column(Text, nullable=False)  # bản gốc, KHÔNG chỉnh sửa
    normalized_text = Column(Text, nullable=False)
    status = Column(SAEnum(ScanStatus, name="scan_status"), nullable=False, default=ScanStatus.PENDING)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("length(raw_content) between 1 and 5000", name="ck_scan_request_raw_content_len"),
        Index("idx_scan_request_device_created", "device_id", "created_at"),
        Index("idx_scan_request_user_created", "user_id", "created_at"),
    )


# =========================================================
# TABLE: scan_entity — Thực thể trích xuất từ nội dung
# =========================================================
class ScanEntity(Base):
    __tablename__ = "scan_entity"

    id = uuid_pk()
    scan_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scan_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type = Column(SAEnum(EntityType, name="entity_type"), nullable=False)
    raw_value = Column(String(500), nullable=False)
    normalized_value = Column(String(500), nullable=False)  # E.164 cho phone, domain cho url
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_scan_entity_scan_request_id", "scan_request_id"),
        Index("idx_scan_entity_normalized_value", "normalized_value"),
    )


# =========================================================
# TABLE: scan_signal — Mỗi bằng chứng góp điểm (AT-03: minh bạch)
# =========================================================
class ScanSignal(Base):
    __tablename__ = "scan_signal"

    id = uuid_pk()
    scan_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scan_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(SAEnum(SignalSource, name="signal_source"), nullable=False)
    rule_code = Column(String(50), nullable=True)  # bắt buộc khi source=RULE
    score = Column(Integer, nullable=False)  # 0..100
    reason_text = Column(Text, nullable=False)  # câu hiển thị (BR-01-12)
    evidence = Column(JSONB, nullable=True)  # đoạn text khớp, entity liên quan
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("score between 0 and 100", name="ck_scan_signal_score_range"),
        CheckConstraint(
            "(source != 'RULE') OR (rule_code IS NOT NULL)",
            name="ck_scan_signal_rule_code_required",
        ),
        Index("idx_scan_signal_scan_request_id", "scan_request_id"),
    )


# =========================================================
# TABLE: scan_result — Kết luận cuối của một lượt quét
# =========================================================
class ScanResult(Base):
    __tablename__ = "scan_result"

    id = uuid_pk()
    scan_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scan_request.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    risk_level = Column(SAEnum(RiskLevel, name="risk_level"), nullable=False)
    final_score = Column(Integer, nullable=False)  # 0..100
    rule_score = Column(Integer, nullable=False)
    ai_score = Column(Integer, nullable=True)  # null khi AI không khả dụng
    ai_available = Column(Boolean, nullable=False, default=True)
    has_hard_override = Column(Boolean, nullable=False, default=False)  # BR-01-1
    recommended_action = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("final_score between 0 and 100", name="ck_scan_result_final_score_range"),
    )


# =========================================================
# TABLE: blacklist_entity — Thực thể đã xác nhận lừa đảo
# =========================================================
class BlacklistEntity(Base):
    __tablename__ = "blacklist_entity"

    id = uuid_pk()
    entity_type = Column(SAEnum(EntityType, name="entity_type_blacklist"), nullable=False)
    normalized_value = Column(String(500), nullable=False)
    source = Column(SAEnum(BlacklistSource, name="blacklist_source"), nullable=False)
    confidence = Column(Integer, nullable=False, default=100)  # 0..100 — xem Mục treo #4
    report_count = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_value", name="uq_blacklist_entity_type_value"),
        Index("idx_blacklist_entity_normalized_value_active","normalized_value",postgresql_where=("is_active = true"),),
    )


# =========================================================
# TABLE: scoring_rule — Rule engine lưu DB (DD-02)
# =========================================================
class ScoringRule(Base):
    __tablename__ = "scoring_rule"

    id = uuid_pk()
    rule_code = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=False)
    pattern = Column(Text, nullable=False)  # regex hoặc danh sách từ khóa
    pattern_type = Column(String(20), nullable=False)  # regex | keyword_list | tld_list
    score = Column(Integer, nullable=False)
    reason_text = Column(Text, nullable=False)  # câu hiển thị khi khớp
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("score between 0 and 100", name="ck_scoring_rule_score_range"),
    )


# =========================================================
# TABLE: app_config — Ngưỡng & tham số (cấm hardcode — L0.3 mục 7)
# =========================================================
class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String(100), primary_key=True)  # vd: threshold.nghi_ngo
    value = Column(Text, nullable=False)
    value_type = Column(String(20), nullable=False)  # int | float | string | bool
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# =========================================================
# TABLE: scam_report — FR-04 [KHUNG, cần hoàn thiện khi đặc tả FR-04]
# NOTE: cơ chế duyệt & ngưỡng tự động active — CHƯA CHỐT (xem PL.3 #6)
# =========================================================
class ScamReport(Base):
    __tablename__ = "scam_report"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False)  # BẮT BUỘC đăng nhập
    entity_type = Column(SAEnum(EntityType, name="entity_type_report"), nullable=False)
    normalized_value = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(ReportStatus, name="report_status"), nullable=False, default=ReportStatus.PENDING)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
