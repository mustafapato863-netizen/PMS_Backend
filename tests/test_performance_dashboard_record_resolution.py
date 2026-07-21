from types import SimpleNamespace

from models.schemas import EvaluationData, PerformanceRecord
from services.dashboard_record_service import DashboardRecordService


def _sql_record(*, employee_id="IN-1", month="June", score=82, grade="C", payload=None):
    team = SimpleNamespace(name="Inbound", db_name="Inbound", display_name=None)
    employee = SimpleNamespace(
        employee_id=employee_id,
        name="Inbound Agent",
        team=team,
        region="EGY",
        position_name=None,
    )
    return SimpleNamespace(
        id=f"sql-{employee_id}",
        employee=employee,
        month=month,
        year=2026,
        region="EGY",
        performance_level="Employee",
        position_name=None,
        status="Meets",
        score=score,
        grade=grade,
        upload_id=None,
        record_payload=payload,
        kpi_values=[],
    )


class _SQLRepositoryStub:
    rows = []
    last_filters = None

    def __init__(self, _db, _model):
        pass

    def get_dashboard_records(self, **filters):
        type(self).last_filters = filters
        return list(type(self).rows)


class _JSONRepositoryStub:
    def get_all(self):
        return []


def _service(rows):
    _SQLRepositoryStub.rows = rows
    return DashboardRecordService(
        object(),
        json_repository=_JSONRepositoryStub(),
        sql_repository_cls=_SQLRepositoryStub,
    )


def test_dashboard_uses_persisted_payload_and_database_score_as_canonical():
    rich_record = PerformanceRecord(
        id="legacy-id",
        employee_id="IN-1",
        employee_name="Old name",
        team="Inbound",
        month="June",
        year=None,
        actual={"attend_rate": 0.72, "booking_rate": 0.51},
        raw_data={"A.Attend%": 0.72, "T.Attend%": 0.75},
        evaluation=EvaluationData(score=0, grade="E", suggested_action="Coach"),
    )

    records = _service([
        _sql_record(score=91.3, grade="B", payload=rich_record.model_dump(mode="json"))
    ]).list_records(team="Inbound", month="June", year=2026)

    assert len(records) == 1
    assert records[0].year == 2026
    assert records[0].actual.attend_rate == 0.72
    assert records[0].raw_data["T.Attend%"] == 0.75
    assert records[0].evaluation.score == 91.3
    assert records[0].evaluation.grade == "B"
    assert records[0].evaluation.suggested_action == "Coach"
    assert _SQLRepositoryStub.last_filters["team"] == "Inbound"
    assert _SQLRepositoryStub.last_filters["month"] == "June"


def test_dashboard_falls_back_to_relational_record_when_payload_is_missing():
    records = _service([_sql_record(score=88.4, grade="C", payload=None)]).list_records()

    assert len(records) == 1
    assert records[0].employee_id == "IN-1"
    assert records[0].year == 2026
    assert records[0].evaluation.score == 88.4
    assert records[0].raw_data == {}


def test_analysis_records_share_the_dashboard_source():
    records = _service([_sql_record(score=90, grade="B")]).list_analysis_records()

    assert len(records) == 1
    assert records[0].evaluation.score == 90
