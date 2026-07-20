from types import SimpleNamespace

from api.routers import performance as performance_router
from models.schemas import EvaluationData, PerformanceRecord
from services.dashboard_record_service import DashboardRecordService


class _SQLRepositoryStub:
    def __init__(self, _db, _model):
        pass

    def get_dashboard_record_keys(self, **_filters):
        return [
            ("LEGACY-1", "Inbound", "June", 2026),
            ("MARKETING-1", "Marketing", "June", 2026),
        ]


class _JSONRepositoryStub:
    def __init__(self):
        self.records = [
            SimpleNamespace(
                employee_id="LEGACY-1",
                team="Inbound",
                month="June",
                year=None,
                performance_level="Employee",
            ),
            SimpleNamespace(
                employee_id="MARKETING-1",
                team="Marketing",
                month="June",
                year=2026,
                performance_level="Employee",
            ),
        ]

    def get_filtered_by_keys(self, keys):
        return [
            record
            for record in self.records
            if (record.employee_id, record.team, record.month, record.year) in keys
        ]

    def get_filtered(self, **_filters):
        return self.records


def test_unscoped_dashboard_resolves_legacy_yearless_and_current_records(monkeypatch):
    json_repo = _JSONRepositoryStub()
    monkeypatch.setattr(performance_router, "SQLPerformanceRepository", _SQLRepositoryStub)
    monkeypatch.setattr(performance_router, "performance_repo", json_repo)

    records = performance_router._get_dashboard_records(object())

    assert [(record.team, record.year) for record in records] == [
        ("Inbound", None),
        ("Marketing", 2026),
    ]


def test_explicit_year_does_not_include_ambiguous_legacy_yearless_records(monkeypatch):
    json_repo = _JSONRepositoryStub()
    monkeypatch.setattr(performance_router, "SQLPerformanceRepository", _SQLRepositoryStub)
    monkeypatch.setattr(performance_router, "performance_repo", json_repo)

    records = performance_router._get_dashboard_records(object(), year=2026)

    assert [(record.team, record.year) for record in records] == [
        ("Marketing", 2026),
    ]


def test_analysis_records_resolve_legacy_year_and_keep_sql_only_teams():
    inbound_json = PerformanceRecord(
        id="IN-1_June",
        employee_id="IN-1",
        employee_name="Inbound Agent",
        team="Inbound",
        month="June",
        year=None,
        evaluation=EvaluationData(score=82, grade="B"),
    )

    def sql_record(employee_id, team_name, month, score):
        team = SimpleNamespace(name=team_name, display_name=None)
        employee = SimpleNamespace(
            employee_id=employee_id,
            name=f"{team_name} Employee",
            team=team,
            region="EGY",
            position_name="Agent",
        )
        return SimpleNamespace(
            id=f"sql-{employee_id}", employee=employee, month=month, year=2026,
            region="EGY", performance_level="Employee", position_name="Agent",
            status="Meets", score=score, grade="B", kpi_values=[],
        )

    sql_rows = [
        sql_record("IN-1", "Inbound", "June", 82),
        sql_record("SA-1", "Sales", "July", 91),
    ]

    class AnalysisSQLRepository:
        def __init__(self, _db, _model):
            pass

        def get_dashboard_records(self):
            return sql_rows

    class AnalysisJSONRepository:
        def get_all(self):
            return [inbound_json]

    records = DashboardRecordService(
        object(),
        json_repository=AnalysisJSONRepository(),
        sql_repository_cls=AnalysisSQLRepository,
    ).list_analysis_records()

    assert [(record.team, record.year) if isinstance(record, PerformanceRecord) else (record["team"], record["year"]) for record in records] == [
        ("Inbound", 2026),
        ("Sales", 2026),
    ]
    assert records[1]["evaluation"] == {"score": 91.0, "grade": "B"}
