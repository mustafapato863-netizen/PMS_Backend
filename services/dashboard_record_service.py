from __future__ import annotations

from sqlalchemy.orm import Session

from models.models import PerformanceRecord
from repositories.json_repos import JSONPerformanceRepository
from repositories.performance_repository import PerformanceRepository as SQLPerformanceRepository
from utils.team_identity import logical_team_name


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

        # Fallback for production when JSON repositories are empty:
        # Load merged SQL/JSON records from list_analysis_records and apply filters in memory
        analysis_records = self.list_analysis_records()
        if not analysis_records:
            return []

        def get_val(item, key):
            if isinstance(item, dict):
                return item.get(key)
            return getattr(item, key, None)

        def get_eval_val(item, key):
            if isinstance(item, dict):
                ev = item.get("evaluation")
                return ev.get(key) if isinstance(ev, dict) else None
            ev = getattr(item, "evaluation", None)
            return getattr(ev, key, None) if ev else None

        filtered = []
        for r in analysis_records:
            r_team = get_val(r, "team")
            r_month = get_val(r, "month")
            r_emp_id = get_val(r, "employee_id")
            r_grade = get_eval_val(r, "grade")
            r_status = get_val(r, "status")
            r_level = get_val(r, "performance_level")
            r_year = get_val(r, "year")
            r_position = get_val(r, "position")
            r_region = get_val(r, "region")

            if team and str(r_team).lower() != str(team).lower():
                continue
            if month and month != "All" and str(r_month).lower() != str(month).lower():
                continue
            if employee_id and str(r_emp_id) != str(employee_id):
                continue
            if grade and str(r_grade) != str(grade):
                continue
            if status and str(r_status).lower() != str(status).lower():
                continue
            if performance_level and performance_level != "All" and str(r_level).lower() != str(performance_level).lower():
                continue
            if year and r_year and int(r_year) != int(year):
                continue
            if position and str(r_position).lower() != str(position).lower():
                continue
            if region and str(r_region).lower() != str(region).lower():
                continue

            filtered.append(r)

        return filtered

    def list_analysis_records(self):
        """Merge rich JSON evidence with every persisted SQL performance row.

        A legacy JSON row without a year is reused only when its identity maps to
        exactly one SQL year. SQL-only rows remain available using their persisted
        score and KPI values, so an incomplete JSON mirror cannot hide a team.
        """
        sql_repository = self.sql_repository_cls(self.db, PerformanceRecord)
        sql_records = sql_repository.get_dashboard_records()
        if not sql_records:
            return self.list_records()

        json_records = self.json_repository.get_all()

        def identity(employee_id, team, month):
            return (
                str(employee_id or "").strip().casefold(),
                str(team or "").strip().casefold(),
                str(month or "").strip().casefold(),
            )

        exact_json = {}
        legacy_json = {}
        for item in json_records:
            key = identity(item.employee_id, item.team, item.month)
            if item.year is None:
                legacy_json[key] = item
            else:
                exact_json[(*key, int(item.year))] = item

        sql_years = {}
        for item in sql_records:
            team_name = logical_team_name(item.employee.team)
            key = identity(item.employee.employee_id, team_name, item.month)
            sql_years.setdefault(key, set()).add(int(item.year))

        result = []
        for item in sql_records:
            employee = item.employee
            team_name = logical_team_name(employee.team)
            key = identity(employee.employee_id, team_name, item.month)
            rich_record = exact_json.get((*key, int(item.year)))
            if rich_record is None and len(sql_years[key]) == 1:
                rich_record = legacy_json.get(key)
            if rich_record is not None:
                result.append(rich_record.model_copy(update={"year": int(item.year)}))
                continue

            result.append({
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
                "evaluation": {"score": float(item.score), "grade": item.grade},
                "raw_data": {},
                "kpi_values": [
                    {
                        "kpi_key": value.kpi_key,
                        "actual_value": float(value.actual_value),
                        "target_value": float(value.target_value),
                        "achievement_ratio": float(value.achievement_ratio),
                        "weight_applied": float(value.weight_applied),
                        "contribution": float(value.contribution),
                    }
                    for value in item.kpi_values
                ],
            })
        return result
