from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, defer, joinedload

from models.models import GeneratedReport, SavedReportTemplate, UploadLog


class ReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_generated(self, report: GeneratedReport) -> None:
        self.db.add(report)

    def list_generated(
        self,
        *,
        owner_user_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[GeneratedReport], int]:
        query = self.db.query(GeneratedReport).options(defer(GeneratedReport.file_data))
        if owner_user_id is not None:
            query = query.filter(GeneratedReport.created_by_user_id == owner_user_id)
        total = query.count()
        rows = query.order_by(GeneratedReport.created_at.desc()).offset(offset).limit(limit).all()
        return rows, total

    def get_generated(self, report_id: UUID) -> GeneratedReport | None:
        return self.db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()

    def add_saved_template(self, template: SavedReportTemplate) -> None:
        self.db.add(template)

    def list_saved_templates(self, owner_user_id: UUID) -> list[SavedReportTemplate]:
        return (
            self.db.query(SavedReportTemplate)
            .filter(SavedReportTemplate.owner_user_id == owner_user_id)
            .order_by(SavedReportTemplate.updated_at.desc())
            .all()
        )

    def list_upload_logs(self) -> list[UploadLog]:
        return (
            self.db.query(UploadLog)
            .options(joinedload(UploadLog.team))
            .order_by(UploadLog.uploaded_at.desc())
            .all()
        )
