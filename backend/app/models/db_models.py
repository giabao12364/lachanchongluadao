import enum
import re
from typing import Optional
import uuid
import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, Column, Enum as SAEnum, ForeignKey, Index, Integer, String, TIMESTAMP, Text, UniqueConstraint, func, event
from sqlalchemy.orm import Mapper, validates
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


# =========================================================
# ENUMS
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


class OtpPurpose(str, enum.Enum):
    REGISTER = "REGISTER"
    LOGIN = "LOGIN"


# =========================================================
# UUID HELPERS
# =========================================================
def uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def uuid_pk_db_default():
    return Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


# =========================================================
# MODELS
# =========================================================
class AppUser(Base):
    __tablename__ = "app_user"

    id = uuid_pk_db_default()
    phone_number = Column(String(20), unique=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=sa.text("true"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Device(Base):
    __tablename__ = "device"

    id = uuid_pk()
    device_uid = Column(String(128), unique=True, nullable=False)
    platform = Column(String(20), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class ScanRequest(Base):
    __tablename__ = "scan_request"

    id = uuid_pk()
    device_id = Column(UUID(as_uuid=True), ForeignKey("device.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True)
    input_type = Column(SAEnum(InputType, name="input_type"), nullable=False)
    raw_content = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=False)
    status = Column(SAEnum(ScanStatus, name="scan_status"), nullable=False, server_default=sa.text("'PENDING'"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("length(raw_content) between 1 and 5000", name="ck_scan_request_raw_content_len"),
        Index("idx_scan_request_device_created", "device_id", sa.text("created_at DESC")),
        Index("idx_scan_request_user_created", "user_id", sa.text("created_at DESC")),
    )


class ScanEntity(Base):
    __tablename__ = "scan_entity"

    id = uuid_pk()
    scan_request_id = Column(UUID(as_uuid=True), ForeignKey("scan_request.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(SAEnum(EntityType, name="entity_type"), nullable=False)
    raw_value = Column(String(500), nullable=False)
    normalized_value = Column(String(500), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_scan_entity_scan_request_id", "scan_request_id"),
        Index("idx_scan_entity_normalized_value", "normalized_value"),
    )


class ScanSignal(Base):
    __tablename__ = "scan_signal"

    id = uuid_pk()
    scan_request_id = Column(UUID(as_uuid=True), ForeignKey("scan_request.id", ondelete="CASCADE"), nullable=False)
    source = Column(SAEnum(SignalSource, name="signal_source"), nullable=False)
    rule_code = Column(String(50), nullable=True)
    score = Column(Integer, nullable=False)
    reason_text = Column(Text, nullable=False)
    evidence = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("score between 0 and 100", name="ck_scan_signal_score_range"),
        CheckConstraint("(source != 'RULE') OR (rule_code IS NOT NULL)", name="ck_scan_signal_rule_code_required"),
        Index("idx_scan_signal_scan_request_id", "scan_request_id"),
    )


class ScanResult(Base):
    __tablename__ = "scan_result"

    id = uuid_pk()
    scan_request_id = Column(UUID(as_uuid=True), ForeignKey("scan_request.id", ondelete="CASCADE"), unique=True, nullable=False)
    risk_level = Column(SAEnum(RiskLevel, name="risk_level"), nullable=False)
    final_score = Column(Integer, nullable=False)
    rule_score = Column(Integer, nullable=False)
    ai_score = Column(Integer, nullable=True)
    ai_available = Column(Boolean, nullable=False, server_default=sa.text("true"))
    has_hard_override = Column(Boolean, nullable=False, server_default=sa.text("false"))
    recommended_action = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("final_score between 0 and 100", name="ck_scan_result_final_score_range"),
    )


class BlacklistEntity(Base):
    __tablename__ = "blacklist_entity"

    id = uuid_pk()
    entity_type = Column(SAEnum(EntityType, name="entity_type"), nullable=False)
    normalized_value = Column(String(500), nullable=False)
    source = Column(SAEnum(BlacklistSource, name="blacklist_source"), nullable=False)
    confidence = Column(Integer, nullable=False, server_default=sa.text("100"))
    report_count = Column(Integer, nullable=False, server_default=sa.text("1"))
    is_active = Column(Boolean, nullable=False, server_default=sa.text("true"))
    note = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_value", name="uq_blacklist_entity_type_value"),
        Index("idx_blacklist_entity_normalized_value_active", "normalized_value", postgresql_where=sa.text("is_active = true")),
    )


class ScoringRule(Base):
    __tablename__ = "scoring_rule"

    id = uuid_pk()
    rule_code = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=False)
    pattern = Column(Text, nullable=False)
    pattern_type = Column(String(20), nullable=False)
    score = Column(Integer, nullable=False)
    reason_text = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=sa.text("true"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("score between 0 and 100", name="ck_scoring_rule_score_range"),
    )


class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class ScamReport(Base):
    __tablename__ = "scam_report"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False)
    entity_type = Column(SAEnum(EntityType, name="entity_type"), nullable=False)
    normalized_value = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(ReportStatus, name="report_status"), nullable=False, server_default=sa.text("'PENDING'"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "normalized_value", name="uq_scam_report_user_entity_value"),
        Index("idx_scam_report_normalized_value", "normalized_value"),
    )


class ScamPattern(Base):
    __tablename__ = "scam_pattern"

    id = uuid_pk_db_default()
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    image_url = Column(Text, nullable=True)
    description = Column(Text, nullable=False)
    signs = Column(Text, nullable=True)
    example_content = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=sa.text("false"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_scam_pattern_active_created", "is_active", sa.text("created_at DESC")),
        Index("idx_scam_pattern_category", "category"),
        CheckConstraint(
            "NOT (is_active = true AND (BTRIM(signs) = '' OR BTRIM(example_content) = '' OR BTRIM(recommended_action) = ''))",
            name="ck_scam_pattern_active_requires_3blocks",
        ),
    )

    @staticmethod
    def _blank(val) -> bool:
        if val is None:
            return True
        return not str(val).strip()

    @classmethod
    def validate_active_requirements(
        cls,
        is_active,
        signs=None,
        example_content=None,
        recommended_action=None,
        existing_obj: Optional["ScamPattern"] = None,
    ) -> None:
        if not is_active:
            return
        s = signs if signs is not None else (existing_obj.signs if existing_obj else "")
        e = example_content if example_content is not None else (existing_obj.example_content if existing_obj else "")
        r = recommended_action if recommended_action is not None else (existing_obj.recommended_action if existing_obj else "")
        missing = []
        if cls._blank(s):
            missing.append("signs (dấu hiệu)")
        if cls._blank(e):
            missing.append("example_content (ví dụ tin nhắn / cuộc gọi)")
        if cls._blank(r):
            missing.append("recommended_action (khuyến nghị hành động)")
        if missing:
            raise ValueError(
                "BR-03-2: Không thể kích hoạt is_active=true vì thiếu "
                + ", ".join(missing)
                + ". Vui lòng bổ sung đủ 3 khối (signs, example_content, recommended_action)."
            )

    @validates("is_active")
    def _v_active(self, key, value):
        try:
            self.validate_active_requirements(
                is_active=value,
                signs=self.__dict__.get("signs"),
                example_content=self.__dict__.get("example_content"),
                recommended_action=self.__dict__.get("recommended_action"),
                existing_obj=self,
            )
        except AttributeError:
            pass
        return value

    @validates("signs", "example_content", "recommended_action")
    def _v_blocks(self, key, value):
        try:
            curr_active = self.__dict__.get("is_active")
            if curr_active:
                new_s = value if key == "signs" else self.__dict__.get("signs")
                new_e = value if key == "example_content" else self.__dict__.get("example_content")
                new_r = value if key == "recommended_action" else self.__dict__.get("recommended_action")
                self.validate_active_requirements(
                    is_active=True,
                    signs=new_s,
                    example_content=new_e,
                    recommended_action=new_r,
                    existing_obj=self,
                )
        except AttributeError:
            pass
        return value


class OtpRequest(Base):
    __tablename__ = "otp_request"

    id = uuid_pk()
    phone_number = Column(String(20), nullable=False)
    otp_hash = Column(String(255), nullable=False)
    purpose = Column(String(20), nullable=False)
    attempt_count = Column(Integer, nullable=False, server_default=sa.text("0"))
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_otp_request_phone_created", "phone_number", sa.text("created_at DESC")),
    )