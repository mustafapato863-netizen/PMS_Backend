from __future__ import annotations

from sqlalchemy.orm import Session

from models.models import PerformanceRecord
from repositories.json_repos import JSONPerformanceRepository
from repositories.performance_repository import PerformanceRepository as SQLPerformanceRepository


class DashboardRecordService:
    """Canonical SQL-scoped resolver for dashboard/report performance records."""

    def __init__(
        self,
        db: Session,
        json_repository: JSONPerformanceRepository | None = None,
        sql_repository_cls=SQLPerformanceRepository,
    ):
        self.db = db
        self.json_repository = json_repository or JSONPerformanceRepository()
        self.sql_repository_cls = sql_repository_cls

    def list_records(
        self,
        *,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
    ):
        sql_repository = self.sql_repository_cls(self.db, PerformanceRecord)
        try:
            keys = sql_repository.get_dashboard_record_keys(
                team=team,
                month=month,
                employee_id=employee_id,
                grade=grade,
                status=status,
                performance_level=performance_level,
                year=year,
                position=position,
                region=region,
            )
        except Exception:
            keys = []

        if keys:
            key_set = set(keys)
            if year is None:
                key_set.update(
                    (employee_key, team_key, month_key, None)
                    for employee_key, team_key, month_key, _record_year in keys
                )
            matched = self.json_repository.get_filtered_by_keys(key_set)
            if performance_level:
                matched = [record for record in matched if record.performance_level == performance_level]
            if matched:
                return matched

        return self.json_repository.get_filtered(
            team=team,
            month=month,
            employee_id=employee_id,
            grade=grade,
            status=status,
            performance_level=performance_level,
            year=year,
            position=position,
            region=region,
        )
