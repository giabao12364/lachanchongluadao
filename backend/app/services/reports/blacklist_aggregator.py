from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.db_models import AppConfig, BlacklistEntity, BlacklistSource, EntityType

DEFAULT_AUTO_ACTIVE_THRESHOLD = 3
DEFAULT_AUTO_ACTIVE_CONFIDENCE = 70  # chỉ dùng khi app_config chưa seed key này


def _get_config_int(db: Session, key: str, default: int) -> int:
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    return int(row.value) if row else default


def _get_auto_active_threshold(db: Session) -> int:
    # BR-04-1 (DD-06) — L4.4: report.auto_active_threshold = 3
    return _get_config_int(db, "report.auto_active_threshold", DEFAULT_AUTO_ACTIVE_THRESHOLD)


def _get_auto_active_confidence(db: Session) -> int:
    # BR-04-1 — L4.4: report.community_confidence = 70
    # (trước đây hardcode AUTO_ACTIVE_CONFIDENCE=70, không đọc app_config — SPEC VIOLATION đã sửa)
    return _get_config_int(db, "report.community_confidence", DEFAULT_AUTO_ACTIVE_CONFIDENCE)


def register_independent_report(
    db: Session, entity_type: EntityType, normalized_value: str
) -> BlacklistEntity:
    """
    Ghi nhận 1 report độc lập (BR-04-1). Tăng report_count; đủ ngưỡng thì
    tự động bật is_active=true, confidence=<report.community_confidence>,
    source=COMMUNITY.

    Dùng UPSERT nguyên tử (INSERT ... ON CONFLICT) thay vì SELECT-rồi-INSERT:
    nếu 2 user report cùng lúc 1 entity HOÀN TOÀN MỚI, cách SELECT-rồi-INSERT
    cũ sẽ để 1 trong 2 transaction dính IntegrityError (vi phạm
    unique(entity_type, normalized_value)) và bị rollback toàn bộ, kể cả
    ScamReport của người dùng hợp lệ đó — false failure không cần thiết.
    UPSERT giao cho Postgres xử lý atomic ở tầng engine, không còn khoảng hở.

    KHÔNG tự commit() ở đây — để report_service.create_report() quyết định
    khi nào chốt transaction, đảm bảo ScamReport + blacklist_entity nằm
    trong CÙNG 1 giao dịch (EX-04-6: không trả kết quả nửa vời).
    """
    threshold = _get_auto_active_threshold(db)
    confidence = _get_auto_active_confidence(db)

    upsert_stmt = (
        pg_insert(BlacklistEntity)
        .values(
            entity_type=entity_type,
            normalized_value=normalized_value,
            source=BlacklistSource.COMMUNITY,
            confidence=0,
            report_count=1,
            is_active=False,
        )
        .on_conflict_do_update(
            index_elements=[BlacklistEntity.entity_type, BlacklistEntity.normalized_value],
            set_={"report_count": BlacklistEntity.report_count + 1},
        )
        .returning(
            BlacklistEntity.id,
            BlacklistEntity.report_count,
            BlacklistEntity.is_active,
        )
    )
    entity_id, report_count, is_active = db.execute(upsert_stmt).one()

    if report_count >= threshold and not is_active:
        # UPDATE có điều kiện is_active=false trong WHERE -> nếu 2 transaction
        # cùng chạm ngưỡng cùng lúc, chỉ 1 cái khớp điều kiện và thắng, cái
        # còn lại UPDATE 0 dòng (no-op), không lỗi, không cần try/except.
        db.execute(
            update(BlacklistEntity)
            .where(
                BlacklistEntity.id == entity_id,
                BlacklistEntity.is_active.is_(False),
            )
            .values(
                is_active=True,
                confidence=confidence,
                source=BlacklistSource.COMMUNITY,
            )
        )

    db.flush()
    return db.get(BlacklistEntity, entity_id)