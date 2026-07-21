from __future__ import annotations

from sqlalchemy.orm import Session

from models.models import PerformanceRecord
from repositories.json_repos import JSONPerformanceRepository
from repositories.performance_repository import PerformanceRepository as SQLPerformanceRepository
from utils.team_identity import logical_team_name
from config.loader import ConfigurationError, load_team_config, resolve_team_config
from models.schemas import PerformanceRecord as SchemaPerformanceRecord
from pydantic import ValidationError


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
        records = sql_repository.get_dashboard_records(
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
        
        result = []
        for item in records:
            employee = item.employee
            team_name = logical_team_name(employee.team)

            payload = getattr(item, "record_payload", None)
            if isinstance(payload, dict):
                try:
                    rich_record = SchemaPerformanceRecord.model_validate(payload)
                    rich_evaluation = rich_record.evaluation.model_copy(
                        update={"score": float(item.score), "grade": item.grade}
                    )
                    result.append(rich_record.model_copy(update={
                        "id": str(item.id),
                        "employee_id": str(employee.employee_id),
                        "employee_name": str(employee.name),
                        "team": team_name,
                        "month": str(item.month),
                        "year": int(item.year),
                        "region": item.region or employee.region,
                        "performance_level": str(item.performance_level),
                        "position": item.position_name or employee.position_name,
                        "status": item.status,
                        "upload_id": str(item.upload_id) if getattr(item, "upload_id", None) else None,
                        "evaluation": rich_evaluation,
                    }))
                    continue
                except ValidationError:
                    # Older/partial payloads remain readable from relational
                    # columns.  A malformed payload must not hide the record.
                    pass

            config_by_key = {}
            try:
                config = resolve_team_config(
                    load_team_config(team_name),
                    str(item.performance_level),
                    item.position_name or employee.position_name,
                )
                config_by_key = {str(kpi.get("key")): kpi for kpi in config.get("kpis", [])}
            except (ConfigurationError, KeyError, TypeError):
                config_by_key = {}

            kpi_values = [
                {
                    "kpi_key": value.kpi_key,
                    "label": config_by_key.get(value.kpi_key, {}).get("label", value.kpi_key),
                    "perspective": config_by_key.get(value.kpi_key, {}).get("perspective"),
                    "unit": config_by_key.get(value.kpi_key, {}).get("unit", "number"),
                    "color": config_by_key.get(value.kpi_key, {}).get("color", "#3B82F6"),
                    "direction": config_by_key.get(value.kpi_key, {}).get("direction", "higher_better"),
                    "actual_value": float(value.actual_value),
                    "target_value": float(value.target_value),
                    "achievement_ratio": (
                        float(value.achievement_ratio) / 100.0
                        if float(value.achievement_ratio) > 2.0
                        else float(value.achievement_ratio)
                    ),
                    "weight_applied": float(value.weight_applied),
                    "contribution": (
                        float(value.contribution) / 100.0
                        if float(value.contribution) > 1.0
                        else float(value.contribution)
                    ),
                }
                for value in item.kpi_values
            ]
            
            result.append(SchemaPerformanceRecord(
                id=str(item.id),
                employee_id=str(employee.employee_id),
                employee_name=str(employee.name),
                team=team_name,
                month=str(item.month),
                year=int(item.year),
                region=item.region or employee.region,
                performance_level=str(item.performance_level),
                position=item.position_name or employee.position_name,
                status=item.status,
                evaluation={"score": float(item.score), "grade": item.grade},
                raw_data={},
                kpi_values=kpi_values,
            ))
            
        return result

    def list_analysis_records(self):
        """Return the same canonical persisted records used by dashboards."""
        return self.list_records()

