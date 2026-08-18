import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Text, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class AppUser(Base):
    __tablename__ = "app_user"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)
    role = Column(String(50), default="user")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    scan_requests = relationship("ScanRequest", back_populates="user", cascade="all, delete-orphan")
    scam_reports = relationship("ScamReport", back_populates="reporter", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "device"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(String(255), unique=True, nullable=False)
    device_name = Column(String(255), nullable=True)
    os_type = Column(String(50), nullable=True)
    os_version = Column(String(50), nullable=True)
    app_version = Column(String(50), nullable=True)
    fcm_token = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("AppUser", back_populates="devices")


class ScoringRule(Base):
    __tablename__ = "scoring_rule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_code = Column(String(100), unique=True, nullable=False)
    rule_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    score_value = Column(Float, nullable=False)
    condition_pattern = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    signals = relationship("ScanSignal", back_populates="rule")


class ScanRequest(Base):
    __tablename__ = "scan_request"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    scan_type = Column(String(50), nullable=False)
    raw_content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=True)
    status = Column(String(50), default="pending")
    client_ip = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("AppUser", back_populates="scan_requests")
    entities = relationship("ScanEntity", back_populates="scan_request", cascade="all, delete-orphan")
    signals = relationship("ScanSignal", back_populates="scan_request", cascade="all, delete-orphan")
    result = relationship("ScanResult", back_populates="scan_request", uselist=False, cascade="all, delete-orphan")


class ScanEntity(Base):
    __tablename__ = "scan_entity"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_request_id = Column(UUID(as_uuid=True), ForeignKey("scan_request.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_value = Column(String(500), nullable=False)
    risk_level = Column(String(50), nullable=True)
    matched_blacklist_id = Column(UUID(as_uuid=True), ForeignKey("blacklist_entity.id"), nullable=True)
    extra_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    scan_request = relationship("ScanRequest", back_populates="entities")
    blacklist_entry = relationship("BlacklistEntity", back_populates="scan_matches")


class ScanSignal(Base):
    __tablename__ = "scan_signal"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_request_id = Column(UUID(as_uuid=True), ForeignKey("scan_request.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("scoring_rule.id"), nullable=True)
    signal_code = Column(String(100), nullable=False)
    signal_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    score_contribution = Column(Float, nullable=False)
    evidence = Column(Text, nullable=True)
    severity = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    scan_request = relationship("ScanRequest", back_populates="signals")
    rule = relationship("ScoringRule", back_populates="signals")


class ScanResult(Base):
    __tablename__ = "scan_result"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_request_id = Column(UUID(as_uuid=True), ForeignKey("scan_request.id", ondelete="CASCADE"), unique=True, nullable=False)
    total_score = Column(Float, nullable=False)
    risk_level = Column(String(50), nullable=False)
    summary = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    is_scam = Column(Boolean, default=False)
    confidence = Column(Float, nullable=True)
    extra_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    scan_request = relationship("ScanRequest", back_populates="result")


class BlacklistEntity(Base):
    __tablename__ = "blacklist_entity"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String(50), nullable=False)
    entity_value = Column(String(500), nullable=False)
    source = Column(String(255), nullable=True)
    risk_level = Column(String(50), default="high")
    is_active = Column(Boolean, default=True)
    report_count = Column(Integer, default=0)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scan_matches = relationship("ScanEntity", back_populates="blacklist_entry")


class ScamReport(Base):
    __tablename__ = "scam_report"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scam_type = Column(String(100), nullable=True)
    loss_amount = Column(Float, default=0)
    currency = Column(String(10), default="VND")
    evidence_urls = Column(JSON, nullable=True)
    contact_info = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    review_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reported_at = Column(DateTime, default=datetime.utcnow)

    reporter = relationship("AppUser", back_populates="scam_reports")


class AppConfig(Base):
    __tablename__ = "app_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(Text, nullable=True)
    config_type = Column(String(50), default="string")
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OtpRequest(Base):
    __tablename__ = "otp_request"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String(20), nullable=False)
    otp_code = Column(String(10), nullable=False)
    otp_hash = Column(String(255), nullable=False)
    purpose = Column(String(50), nullable=False)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScamPattern(Base):
    __tablename__ = "scam_pattern"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    image_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    signs = Column(Text, nullable=True)
    example_content = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
