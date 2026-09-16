from sqlalchemy.orm import Session

from app.models.db_models import AppConfig, BlacklistEntity, BlacklistSource, EntityType

DEFAULT_AUTO_ACTIVE_THRESHOLD = 3
AUTO_ACTIVE_CONFIDENCE = 70


def _get_auto_active_threshold(db: Session) -> int:
    row = (
        db.query(AppConfig)
        .filter(AppConfig.key == "report.auto_active_threshold")
        .first()
    )
    return int(row.value) if row else DEFAULT_AUTO_ACTIVE_THRESHOLD


def register_independent_report(
    db: Session, entity_type: EntityType, normalized_value: str
) -> BlacklistEntity:
    """
    Ghi nhận 1 report độc lập (BR-04-1). Tăng report_count; đủ ngưỡng thì
    tự động bật is_active=true, confidence=70, source=COMMUNITY.

    KHÔNG tự commit() ở đây (khác bản gốc) — để hàm gọi (report_service.
    create_report) quyết định khi nào chốt transaction, đảm bảo việc tạo
    ScamReport + cập nhật blacklist_entity nằm trong CÙNG 1 giao dịch
    (EX-04-6: không trả kết quả nửa vời).
    """
    entity = (
        db.query(BlacklistEntity)
        .filter(
            BlacklistEntity.entity_type == entity_type,
            BlacklistEntity.normalized_value == normalized_value,
        )
        .first()
    )

    threshold = _get_auto_active_threshold(db)

    if entity is None:
        entity = BlacklistEntity(
            entity_type=entity_type,
            normalized_value=normalized_value,
            source=BlacklistSource.COMMUNITY,
            confidence=0,
            report_count=1,
            is_active=False,
        )
        db.add(entity)
    else:
        entity.report_count += 1

    if entity.report_count >= threshold and not entity.is_active:
        entity.is_active = True
        entity.confidence = AUTO_ACTIVE_CONFIDENCE
        entity.source = BlacklistSource.COMMUNITY

    db.flush()
    return entity