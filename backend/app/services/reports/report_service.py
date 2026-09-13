
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.db_models import ScamReport, EntityType, ReportStatus
from app.services.reports.report_validator import ValidatedReportEntity
from app.services.reports.blacklist_aggregator import register_independent_report


@dataclass
class CreateReportResult:
    report_id: UUID
    status: str
    is_duplicate: bool  


def create_report(
    db: Session,
    user_id: UUID,
    entity: ValidatedReportEntity,
    description: str | None = None,
) -> CreateReportResult:
   
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
        db.flush()  
    except IntegrityError:
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

    try:
        register_independent_report(db, entity.entity_type, entity.normalized_value)
        db.commit()  
    except Exception:
        db.rollback()  
        raise

    db.refresh(new_report)
    return CreateReportResult(
        report_id=new_report.id,
        status=new_report.status.value,
        is_duplicate=False,
    )