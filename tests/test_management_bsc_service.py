import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.models import Base, Team
from services.management_bsc_service import ManagementBSCService, _highest_position


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _base_config():
    return {
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "balanced_scorecard": {
            "enabled": True,
            "perspectives": [
                {"key": "Financial", "label": "Financial", "display_order": 1},
                {"key": "Customer", "label": "Customer", "display_order": 2},
                {"key": "Internal Process", "label": "Internal Process", "display_order": 3},
                {"key": "Learning & Growth", "label": "Learning & Growth", "display_order": 4},
            ],
            "strategy_map_links": [],
        },
    }


def _seed_team(session, name="Sales"):
    team = Team(id=uuid.uuid4(), name=name, db_name=name, region="EGY")
    session.add(team)
    session.commit()
    return team


def test_highest_position_uses_org_seniority():
    assert _highest_position({"Account Manager", "Finance Manager", "Sales Director"}) == "Sales Director"


def test_employee_override_beats_position_config():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
        {
            "employee_id": "EMP-2",
            "team": "Sales",
            "employee_name": "Two",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
        {
            "employee_id": "EMP-3",
            "team": "Sales",
            "employee_name": "Three",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 50.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
    ]

    result = service.import_template_rows(rows=rows, updated_by="tester")
    data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-3"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )

    revenue = next(row for row in data["kpi_table"] if row["kpi_key"] == "revenue_achievement")
    assert result["config_rows"] == 2
    assert revenue["score"] == 200.0
    assert data["team"]["top_position"] == "Sales Manager"
    assert data["selection"]["config_scope_summary"]["employee_overrides"] == 1
    session.close()


def test_historical_month_uses_exact_period_config():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "June",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 50.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
    ]

    service.import_template_rows(rows=rows, updated_by="tester")

    may_data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )
    june_data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="June",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )

    may_score = next(row for row in may_data["kpi_table"] if row["kpi_key"] == "revenue_achievement")["score"]
    june_score = next(row for row in june_data["kpi_table"] if row["kpi_key"] == "revenue_achievement")["score"]
    assert may_score == 100.0
    assert june_score == 200.0
    assert may_data["selection"]["effective_month"] == "May"
    assert june_data["selection"]["effective_month"] == "June"
    session.close()


def test_missing_management_config_returns_real_empty_response():
    session = _db()
    _seed_team(session, "Sales")
    data = ManagementBSCService(session).build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=[],
        history_months=6,
        selected_kpi=None,
        base_config=_base_config(),
    )

    assert data["kpi_table"] == []
    assert data["perspectives"] == []
    assert data["selection"]["data_source"] == "database_config"
    session.close()


def test_import_template_rows_groups_by_team_column():
    session = _db()
    _seed_team(session, "Sales")
    _seed_team(session, "CSR")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
        {
            "employee_id": "EMP-2",
            "team": "CSR",
            "employee_name": "Two",
            "position": "CSR Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Customer",
            "kpi_label": "CSAT",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 90.0,
            "target_unit": "%",
            "actual_value": 91.0,
        },
    ]

    result = service.import_template_rows(rows=rows, updated_by="tester")

    assert result["teams"] == ["CSR", "Sales"]
    sales_data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )
    csr_data = service.build_scorecard_dataset(
        team_name="CSR",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-2"],
        history_months=6,
        selected_kpi="csat",
        base_config=_base_config(),
    )

    assert sales_data["kpi_table"][0]["kpi_key"] == "revenue_achievement"
    assert csr_data["kpi_table"][0]["kpi_key"] == "csat"
    session.close()


def test_import_template_rows_creates_missing_team_from_template():
    session = _db()
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Call Center",
            "employee_name": "One",
            "position": "Call Center Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Customer",
            "kpi_label": "CSAT",
            "direction": "higher_better",
            "weight": 1.0,
            "target_value": 90.0,
            "target_unit": "%",
            "actual_value": 91.0,
        },
    ]

    result = service.import_template_rows(rows=rows, updated_by="tester")

    assert result["teams"] == ["Call Center"]
    assert session.query(Team).filter(Team.name == "Call Center").first() is not None
    session.close()


def test_delete_upload_batch_removes_management_rows():
    session = _db()
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Call Center",
            "employee_name": "One",
            "position": "Call Center Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Customer",
            "kpi_label": "CSAT",
            "direction": "higher_better",
            "weight": 1.0,
            "target_value": 90.0,
            "target_unit": "%",
            "actual_value": 91.0,
        },
    ]

    result = service.import_template_rows(rows=rows, updated_by="tester", source_filename="dummy.xlsx")
    deleted = service.delete_upload_batch(result["upload_batch_id"])

    assert deleted["config_rows_deleted"] > 0
    assert deleted["snapshot_rows_deleted"] > 0
    assert service.list_upload_batches() == []
    session.close()
