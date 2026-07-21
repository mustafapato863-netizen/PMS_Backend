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
        team=team,
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


def _service(rows):
    _SQLRepositoryStub.rows = rows
    return DashboardRecordService(
        object(),
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


def test_dashboard_merges_relational_kpi_breakdown_into_rich_payload():
    rich_record = PerformanceRecord(
        id="legacy-id",
        employee_id="IN-1",
        employee_name="Inbound Agent",
        team="Inbound",
        month="June",
        year=2026,
        evaluation=EvaluationData(score=91.3, grade="B"),
        kpi_values=[],
    )
    row = _sql_record(payload=rich_record.model_dump(mode="json"))
    row.kpi_values = [
        SimpleNamespace(
            kpi_key="attendance",
            actual_value=0.678,
            target_value=0.75,
            achievement_ratio=0.904,
            weight_applied=0.70,
            contribution=0.6328,
        )
    ]

    [record] = _service([row]).list_records()

    assert len(record.kpi_values) == 1
    assert record.kpi_values[0]["weight_applied"] == 0.70
    assert record.kpi_values[0]["contribution"] == 0.6328


def test_dashboard_repairs_legacy_call_center_kpi_evidence_from_the_original_row():
    rich_record = PerformanceRecord(
        id="legacy-id",
        employee_id="IN-1",
        employee_name="Inbound Agent",
        team="Inbound",
        month="May",
        year=2026,
        raw_data={
            "A.Attend%": 0.671,
            "Attend%Ach%": 0.8946666667,
            "A.Booking%": 0.548,
            "Booking%Ach%": 1.2177777778,
            "A.QualityScore": 0.977,
            "QualityTargetAch%": 1.0284210526,
            "AHT_Minutes": 2.7333333333,
            "AHTAch%": 0.9146341463,
            "A.UTZ%": 0.821,
            "UTZ%Ach%": 0.9658823529,
        },
        evaluation=EvaluationData(score=82.6, grade="C"),
    )
    row = _sql_record(month="May", payload=rich_record.model_dump(mode="json"))
    row.kpi_values = [
        SimpleNamespace(
            kpi_key=key,
            actual_value=0,
            target_value=0,
            achievement_ratio=0,
            weight_applied=weight,
            contribution=0,
        )
        for key, weight in [
            ("Attendance", 0.70),
            ("Booking", 0.10),
            ("Quality", 0.05),
            ("AHT", 0.05),
            ("Other", 0.10),
        ]
    ]

    [record] = _service([row]).list_records()
    by_key = {item["kpi_key"]: item for item in record.kpi_values}

    assert by_key["Attendance"]["target_value"] == 0.75
    assert by_key["Quality"]["target_value"] == 0.95
    assert by_key["AHT"]["target_value"] == 2.5
    assert by_key["Other"]["label"] == "Utilization"
    assert by_key["Other"]["target_value"] == 0.85
    assert by_key["Attendance"]["weight_applied"] == 0.70


def test_dashboard_falls_back_to_relational_record_when_payload_is_missing():
    records = _service([_sql_record(score=88.4, grade="C", payload=None)]).list_records()

    assert len(records) == 1
    assert records[0].employee_id == "IN-1"
    assert records[0].year == 2026
    assert records[0].evaluation.score == 88.4
    assert records[0].raw_data == {}


def test_dashboard_uses_the_historical_record_team_not_the_employees_current_team():
    row = _sql_record(payload=None)
    row.employee.team = SimpleNamespace(name="Outbound", db_name="Outbound", display_name=None)

    [record] = _service([row]).list_records()

    assert record.team == "Inbound"


def test_analysis_records_share_the_dashboard_source():
    records = _service([_sql_record(score=90, grade="B")]).list_analysis_records()

    assert len(records) == 1
    assert records[0].evaluation.score == 90
