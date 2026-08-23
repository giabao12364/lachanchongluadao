import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, Boolean, Text, Float,
    CheckConstraint, Index, UniqueConstraint, Enum as SAEnum, func, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base

import enum

Base = declarative_base()


# =========================================================
# ENUMS — giữ nguyên giá trị để không break DB nếu có type cũ
# =========================================================
class InputType(str, enum.Enum):
    TEXT = "TEXT"
    URL = "URL"
    PHONE = "PHONE"
    FILE = "FILE"


class ScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EntityType(str, enum.Enum):
    PHONE = "PHONE"
    URL = "URL"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    EMAIL = "EMAIL"
    OTHER = "OTHER"


class SignalSource(str, enum.Enum):
    RULE = "RULE"
    AI = "AI"
    BLACKLIST = "BLACKLIST"
    MANUAL = "MANUAL"


class RiskLevel(str, enum.Enum):
    AN_TOAN = "AN_TOAN"
    NGHI_NGO = "NGHI_NGO"
    NGUY_HIEM = "NGUY_HIEM"


class BlacklistSource(str, enum.Enum):
    USER_REPORT = "USER_REPORT"
    FEED = "FEED"
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"


class ReportStatus(str, enum.Enum):
    PENDING = "PENDING"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# =========================================================
# app_user — Tài khoản đã đăng ký (FR-05)
# =========================================================
class AppUser(Base):
    __tablename__ = "app_user"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    phone_number = Column(String(20), unique=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    scan_requests = relationship("ScanRequest", back_populates="user", cascade="all, delete-orphan")
    scam_reports = relationship("ScamReport", back_populates="reporter", cascade="all, delete-orphan")


# =========================================================
# device — Định danh người dùng ẩn danh
# =========================================================
class Device(Base):
    __tablename__ = "device"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_uid = Column(String(128), unique=True, nullable=False)
    platform = Column(String(20), nullable=False, default="web")
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("AppUser", back_populates="devices")
    scan_requests = relationship("ScanRequest", back_populates="device", cascade="all, delete-orphan")


# =========================================================
# scan_request — Mỗi lượt quét (FR-01)
# =========================================================
class ScanRequest(Base):
    __tablename__ = "scan_request"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("device.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=True)
    input_type = Column(SAEnum(InputType, name="input_type_enum"), nullable=False)
    raw_content = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=False, default="")
    status = Column(SAEnum(ScanStatus, name="scan_status_enum"), nullable=False, default=ScanStatus.PENDING)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("length(raw_content) BETWEEN 1 AND 5000", name="ck_scan_request_raw_content_len"),
        Index("ix_scan_request_device_id_created_at_desc", "device_id", created_at.desc()),
        Index("ix_scan_request_user_id_created_at_desc", "user_id", created_at.desc()),
    )

    device = relationship("Device", back_populates="scan_requests")
    user = relationship("AppUser", back_populates="scan_requests")
    entities = relationship("ScanEntity", back_populates="scan_request", cascade="all, delete-orphan")
    signals = relationship("ScanSignal", back_populates="scan_request", cascade="all, delete-orphan")
    result = relationship("ScanResult", back_populates="scan_request", uselist=False, cascade="all, delete-orphan")


# =========================================================
# scan_entity — Thực thể trích xuất từ nội dung
# =========================================================
class ScanEntity(Base):
    __tablename__ = "scan_entity"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_request_id = Column(UUID(as_uuid=True), ForeignKey("scan_request.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(SAEnum(EntityType, name="entity_type_enum"), nullable=False)
    raw_value = Column(String(500), nullable=False)
    normalized_value = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_scan_entity_scan_request_id", "scan_request_id"),
        Index("ix_scan_entity_normalized_value", "normalized_value"),
    )

    scan_request = relationship("ScanRequest", back_populates="entities")


# =========================================================
# scan_signal — Mỗi bằng chứng góp điểm (minh bạch AT-03)
# =========================================================
class ScanSignal(Base):
    __tablename__ = "scan_signal"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_request_id = Column(UUID(as_uuid=True), ForeignKey("scan_request.id", ondelete="CASCADE"), nullable=False)
    source = Column(SAEnum(SignalSource, name="signal_source_enum"), nullable=False)
    rule_code = Column(String(50), nullable=True)
    score = Column(Integer, nullable=False, default=0)
    reason_text = Column(Text, nullable=False)
    evidence = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_scan_signal_score_range"),
        CheckConstraint(
            "(source != 'RULE') OR (rule_code IS NOT NULL)",
            name="ck_scan_signal_rule_required_when_rule",
        ),
        Index("ix_scan_signal_scan_request_id", "scan_request_id"),
    )

    scan_request = relationship("ScanRequest", back_populates="signals")


# =========================================================
# scan_result — Kết luận cuối của một lượt quét
# =========================================================
class ScanResult(Base):
    __tablename__ = "scan_result"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scan_request.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    risk_level = Column(SAEnum(RiskLevel, name="risk_level_enum"), nullable=False)
    final_score = Column(Integer, nullable=False, default=0)
    rule_score = Column(Integer, nullable=False, default=0)
    ai_score = Column(Integer, nullable=True)
    ai_available = Column(Boolean, nullable=False, default=True)
    has_hard_override = Column(Boolean, nullable=False, default=False)
    recommended_action = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("final_score BETWEEN 0 AND 100", name="ck_scan_result_final_score_range"),
    )

    scan_request = relationship("ScanRequest", back_populates="result")


# =========================================================
# blacklist_entity — Thực thể đã xác nhận lừa đảo
# =========================================================
class BlacklistEntity(Base):
    __tablename__ = "blacklist_entity"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(SAEnum(EntityType, name="entity_type_enum"), nullable=False)
    normalized_value = Column(String(500), nullable=False)
    source = Column(SAEnum(BlacklistSource, name="blacklist_source_enum"), nullable=False)
    confidence = Column(Integer, nullable=False, default=100)
    report_count = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_value", name="uq_blacklist_entity_type_value"),
        Index("ix_blacklist_entity_normalized_value_active", "normalized_value", postgresql_where=(is_active == True)),
    )


# =========================================================
# scoring_rule — Rule engine lưu DB (DD-02)
# =========================================================
class ScoringRule(Base):
    __tablename__ = "scoring_rule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_code = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=False, default="")
    pattern = Column(Text, nullable=False, default="")
    pattern_type = Column(String(20), nullable=False, default="keyword_list")
    score = Column(Integer, nullable=False, default=0)
    reason_text = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_scoring_rule_score_range"),
    )


# =========================================================
# app_config — Ngưỡng & tham số (cấm hardcode)
# =========================================================
class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), nullable=False, default="string")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


# =========================================================
# scam_report — Báo cáo lừa đảo (FR-04)
# =========================================================
class ScamReport(Base):
    __tablename__ = "scam_report"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(SAEnum(EntityType, name="entity_type_enum"), nullable=False)
    normalized_value = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(ReportStatus, name="report_status_enum"), nullable=False, default=ReportStatus.PENDING)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "normalized_value", name="uq_scam_report_user_entity_value"),
        Index("ix_scam_report_normalized_value", "normalized_value"),
    )

    reporter = relationship("AppUser", back_populates="scam_reports")


# =========================================================
# scam_pattern — Thư viện bài viết mẫu chiêu trò lừa đảo (FR-03)
# =========================================================
class ScamPattern(Base):
    __tablename__ = "scam_pattern"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    image_url = Column(Text, nullable=True)
    description = Column(Text, nullable=False, default="")
    signs = Column(Text, nullable=False, default="")
    example_content = Column(Text, nullable=False, default="")
    recommended_action = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_scam_pattern_active_created_at_desc", "is_active", created_at.desc()),
        Index("ix_scam_pattern_category", "category"),
    )


# =========================================================
# otp_request — Lưu mã OTP (FR-05)
# =========================================================
class OtpRequest(Base):
    __tablename__ = "otp_request"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String(20), nullable=False)
    otp_hash = Column(String(255), nullable=False)
    purpose = Column(String(20), nullable=False, default="LOGIN")
    attempt_count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_otp_request_phone_created_at_desc", "phone_number", created_at.desc()),
    )
