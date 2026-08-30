"""
Tầng 2 — Blacklist Checker (FR-01.6, BR-01-1, BR-01-1b)

Đối chiếu các thực thể đã trích xuất (Tầng 1 — Extractor) với bảng
blacklist_entity. Tầng này KHÔNG tự quyết định risk_level cuối cùng
(việc đó thuộc bước Hợp nhất), chỉ trả về tín hiệu để bước đó dùng.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.db_models import (
    AppConfig,
    BlacklistEntity,
    BlacklistSource,
    EntityType,
    RiskLevel,
)
from app.services.scan.extractor import ExtractedEntity

DEFAULT_HARD_OVERRIDE_CONFIDENCE = 90


_ENTITY_LABEL_VI: dict[EntityType, str] = {
    EntityType.URL: "Đường link này",
    EntityType.DOMAIN: "Tên miền này",
    EntityType.PHONE: "Số này",
    EntityType.BANK_ACCOUNT: "Số tài khoản này",
}

_HARD_OVERRIDE_NOUN: dict[EntityType, str] = {
    EntityType.URL: "trang lừa đảo",
    EntityType.DOMAIN: "trang lừa đảo",
    EntityType.PHONE: "số lừa đảo",
    EntityType.BANK_ACCOUNT: "tài khoản lừa đảo",
}


@dataclass
class BlacklistSignal:
    """Tín hiệu Tầng 2, làm input cho bước Hợp nhất (BR-01-1 -> BR-01-7)."""

    entity: ExtractedEntity
    matched: bool
    has_hard_override: bool  # True -> BR-01-1: ép NGUY_HIEM, tầng sau không được hạ
    capped_risk_level: RiskLevel | None  # BR-01-1b: trần NGHI_NGO; None = không giới hạn
    source: BlacklistSource | None
    confidence: int | None
    reason_text: str | None


def _get_hard_override_confidence(db: Session) -> int:
    """Đọc ngưỡng blacklist.hard_override_confidence từ app_config (KT-03 — cấm hardcode)."""
    row = (
        db.query(AppConfig)
        .filter(AppConfig.key == "blacklist.hard_override_confidence")
        .first()
    )
    return int(row.value) if row else DEFAULT_HARD_OVERRIDE_CONFIDENCE


def _build_reason(entity_type: EntityType, has_hard_override: bool) -> str:
    label = _ENTITY_LABEL_VI.get(entity_type, "Thực thể này")
    if has_hard_override:
        noun = _HARD_OVERRIDE_NOUN.get(entity_type, "lừa đảo")
        return f"{label} đã được xác nhận là {noun}."
    return f"{label} đã bị một số người báo cáo là lừa đảo."


def check_entity_against_blacklist(db: Session, entity: ExtractedEntity) -> BlacklistSignal:
    """Đối chiếu 1 thực thể với blacklist_entity (chỉ xét bản ghi is_active=true)."""
    row = (
        db.query(BlacklistEntity)
        .filter(
            BlacklistEntity.entity_type == entity.entity_type,
            BlacklistEntity.normalized_value == entity.normalized_value,
            BlacklistEntity.is_active.is_(True),
        )
        .first()
    )

    if row is None:
        return BlacklistSignal(
            entity=entity,
            matched=False,
            has_hard_override=False,
            capped_risk_level=None,
            source=None,
            confidence=None,
            reason_text=None,
        )

    threshold = _get_hard_override_confidence(db)
    is_trusted_source = row.source in (BlacklistSource.PUBLIC_FEED, BlacklistSource.MANUAL)
    has_hard_override = is_trusted_source or row.confidence >= threshold

    return BlacklistSignal(
        entity=entity,
        matched=True,
        has_hard_override=has_hard_override,
        capped_risk_level=None if has_hard_override else RiskLevel.NGHI_NGO,
        source=row.source,
        confidence=row.confidence,
        reason_text=_build_reason(entity.entity_type, has_hard_override),
    )


def check_entities_against_blacklist(
    db: Session, entities: list[ExtractedEntity]
) -> list[BlacklistSignal]:
    """Áp check cho toàn bộ danh sách thực thể của 1 lượt quét."""
    return [check_entity_against_blacklist(db, e) for e in entities]