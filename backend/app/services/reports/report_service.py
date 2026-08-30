"""
T-031 — Chống report trùng của cùng user (BR-04-2)
Dựa vào UniqueConstraint(user_id, entity_type, normalized_value) đã có sẵn
trên bảng scam_report (Đức, db_models.py) — DB tự chặn trùng, hàm này chỉ
cần bắt lỗi và trả về kết quả thân thiện, không để crash 500.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.db_models import ScamReport, EntityType
from app.services.reports.report_validator import ValidatedReportEntity
from app.models.db_models import ScamReport, EntityType, ReportStatus


@dataclass
class CreateReportResult:
    report_id: UUID
    status: str
    is_duplicate: bool  # True nếu đây là lần report thứ 2+ trùng của cùng user


def create_report(
    db: Session,
    user_id: UUID,
    entity: ValidatedReportEntity,
    description: str | None = None,
) -> CreateReportResult:
    """
    Tạo 1 report mới. Nếu user này đã report đúng thực thể này rồi (BR-04-2),
    KHÔNG tạo bản ghi mới — trả về report cũ kèm is_duplicate=True.
    """
    existing = (
        db.query(ScamReport)
        .filter(
            ScamReport.user_id == user_id,
            ScamReport.entity_type == entity.entity_type,
            ScamReport.normalized_value == entity.normalized_value,
        )
        .first()
    )
    if existing is not None:
        return CreateReportResult(
            report_id=existing.id,
            status=existing.status.value,
            is_duplicate=True,
        )

    new_report = ScamReport(
        user_id=user_id,
        entity_type=entity.entity_type,
        normalized_value=entity.normalized_value,
        description=description,
        status=ReportStatus.PENDING,
    )
    db.add(new_report)
    try:
        db.commit()
    except IntegrityError:
        # Fallback hiếm gặp: race condition giữa lúc query existing và lúc insert
        # (2 request cùng lúc từ cùng user) -> UniqueConstraint chặn ở tầng DB.
        db.rollback()
        existing = (
            db.query(ScamReport)
            .filter(
                ScamReport.user_id == user_id,
                ScamReport.entity_type == entity.entity_type,
                ScamReport.normalized_value == entity.normalized_value,
            )
            .first()
        )
        return CreateReportResult(
            report_id=existing.id,
            status=existing.status.value,
            is_duplicate=True,
        )

    db.refresh(new_report)
    return CreateReportResult(
        report_id=new_report.id,
        status=new_report.status.value,
        is_duplicate=False,
    )