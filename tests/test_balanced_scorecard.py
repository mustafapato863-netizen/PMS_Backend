from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.dependencies import get_current_user_scope, require_authenticated_scope, user_can_access_team_level
from config.loader import validate_team_config
from models.schemas import EvaluationData, PerformanceRecord
from models.models import Base, Team, User, UserTeamAssignment
from services.balanced_scorecard_service import BalancedScorecardService
from api.routers.performance import get_balanced_scorecard


PERSPECTIVES = [
    {"key": "Financial", "label": "Financial", "display_order": 1},
    {"key": "Customer", "label": "Customer", "display_order": 2},
    {"key": "Internal Process", "label": "Internal Process", "display_order": 3},
    {"key": "Learning & Growth", "label": "Learning & Growth", "display_order": 4},
]


def config():
    return {
        "team": "Test Team",
        "db_name": "Test Team",
        "region": "EGY",
        "employee_id_col": "EmployeeID",
        "employee_name_col": "EmployeeName",
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "balanced_scorecard": {
            "enabled": True,
            "perspectives": PERSPECTIVES,
            "strategy_map_links": [{"from": "Learning & Growth", "to": "Internal Process"}],
        },
        "kpis": [
            {"key": "revenue", "label": "Revenue", "perspective": "Financial", "weight": 0.5, "direction": "higher_better", "unit": "%", "color": "#111111", "actual_col": "A.Revenue", "target_col": "T.Revenue", "rollup": "average"},
            {"key": "cycle", "label": "Cycle Time", "perspective": "Internal Process", "weight": 0.3, "direction": "lower_better", "unit": "days", "color": "#222222", "actual_col": "A.Cycle", "target_col": "T.Cycle", "rollup": "average"},
            {"key": "satisfaction", "label": "Satisfaction", "perspective": "Customer", "weight": 0.2, "direction": "higher_better", "unit": "%", "color": "#333333", "actual_col": "A.Satisfaction", "target_col": "T.Satisfaction", "rollup": "average"},
        ],
    }


def record(employee_id, name, date, revenue_contribution, cycle_contribution):
    return PerformanceRecord(
        id=f"{employee_id}_{date}",
        employee_id=employee_id,
        employee_name=name,
        team="Test Team",
        month="May",
        performance_level="Managerial",
        raw_data={"Date": f"{date}-05-01T00:00:00"},
        evaluation=EvaluationData(score=80, grade="B"),
        kpi_values=[
            {"kpi_key": "revenue", "actual_value": 110, "target_value": 100, "achievement_ratio": 1.1, "weight_applied": 0.5, "contribution": revenue_contribution},
            {"kpi_key": "cycle", "actual_value": 4, "target_value": 5, "achievement_ratio": 1.25, "weight_applied": 0.3, "contribution": cycle_contribution},
        ],
    )


def test_aggregation_uses_contributions_and_preserves_raw_achievement():
    data = BalancedScorecardService.build(
        [record("1", "A", 2025, 0.5, 0.3), record("2", "B", 2025, 0.4, 0.15)],
        config(), "Test Team", "Managerial", "May", 2025,
    )

    assert data["scorecard"]["score"] == pytest.approx(84.375)
    assert data["scorecard"]["coverage"] == pytest.approx(0.8)
    revenue = next(row for row in data["kpi_table"] if row["kpi_key"] == "revenue")
    assert revenue["raw_achievement_ratio"] == pytest.approx(1.1)
    assert revenue["weighted_contribution"] == pytest.approx(0.45)
    assert revenue["score"] == pytest.approx(90)


def test_no_data_is_not_zero_and_employee_filter_is_applied():
    data = BalancedScorecardService.build(
        [record("1", "A", 2025, 0.5, 0.3), record("2", "B", 2025, 0.1, 0.1)],
        config(), "Test Team", "Managerial", "May", 2025, employee_ids=["1"],
    )

    satisfaction = next(row for row in data["kpi_table"] if row["kpi_key"] == "satisfaction")
    customer = next(row for row in data["perspectives"] if row["key"] == "Customer")
    learning = next(row for row in data["perspectives"] if row["key"] == "Learning & Growth")
    assert satisfaction["score"] is None and satisfaction["state"] == "no_data"
    assert customer["score"] is None and customer["state"] == "no_data"
    assert learning["score"] is None and learning["state"] == "not_configured"
    assert data["selection"]["people_count"] == 1
    assert [row["employee_id"] for row in data["contributors"]] == ["1"]


def test_year_is_explicit_and_history_ends_at_selected_period():
    data = BalancedScorecardService.build(
        [record("1", "A", 2025, 0.4, 0.2), record("1", "A", 2026, 0.5, 0.3)],
        config(), "Test Team", "Managerial", "May", 2025,
    )

    assert data["selection"]["year"] == 2025
    assert data["available_periods"] == [{"month": "May", "year": 2025}, {"month": "May", "year": 2026}]
    assert data["history"][-1]["year"] == 2025


def test_bsc_config_validation_rejects_unknown_perspective():
    raw = config()
    raw["performance_levels"] = {"Managerial": {"balanced_scorecard": raw.pop("balanced_scorecard"), "kpis": raw.pop("kpis")}}
    raw["kpis"] = [{"key": "legacy", "label": "Legacy", "weight": 1, "direction": "higher_better", "unit": "%", "color": "#000000", "actual_col": "a", "target_col": "t"}]
    raw["performance_levels"]["Managerial"]["kpis"][0]["perspective"] = "Unknown"

    valid, errors = validate_team_config(raw)
    assert valid is False
    assert any("invalid perspective" in error for error in errors)


def test_level_scope_rejects_legacy_and_cross_level_access(monkeypatch):
    assert user_can_access_team_level({"legacy_unscoped": True}, "Finance", "Managerial") is False
    scope = {
        "legacy_unscoped": False,
        "role": "Manager",
        "accessible_teams": ["Finance"],
        "accessible_team_levels": [("Finance", "Managerial")],
    }
    assert user_can_access_team_level(scope, "Finance", "Managerial") is True
    assert user_can_access_team_level(scope, "Finance", "Corporate") is False

    monkeypatch.setattr("api.dependencies.get_current_user_scope", lambda db, request: {"legacy_unscoped": True})
    with pytest.raises(HTTPException) as exc:
        require_authenticated_scope(None, SimpleNamespace())
    assert exc.value.status_code == 401


def test_endpoint_rejects_employee_before_reading_data():
    with pytest.raises(HTTPException) as exc:
        get_balanced_scorecard(
            request=SimpleNamespace(), db=None, team="Test Team", performance_level="Employee",
            month="May", year=2025, branch=None, employee_ids=[], history_months=6, selected_kpi=None,
        )
    assert exc.value.status_code == 422


def test_endpoint_rejects_people_outside_authorized_context(monkeypatch):
    monkeypatch.setattr("api.routers.performance.require_authenticated_scope", lambda db, request: {"legacy_unscoped": False})
    monkeypatch.setattr("api.routers.performance.user_can_access_team_level", lambda scope, team, level: True)
    monkeypatch.setattr("api.routers.performance.load_team_config", lambda team: {"team": team})
    monkeypatch.setattr("api.routers.performance.resolve_team_config", lambda raw, level: config())
    monkeypatch.setattr("api.routers.performance._get_dashboard_records", lambda *args, **kwargs: [record("1", "A", 2025, 0.5, 0.3)])
    monkeypatch.setattr("api.routers.performance.filter_records_by_scope", lambda records, scope: records)

    with pytest.raises(HTTPException) as exc:
        get_balanced_scorecard(
            request=SimpleNamespace(), db=None, team="Test Team", performance_level="Managerial",
            month="May", year=2025, branch=None, employee_ids=["outside"], history_months=6, selected_kpi=None,
        )
    assert exc.value.status_code == 403


def test_level_specific_access_to_all_teams_does_not_become_general_manager():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(
        id=uuid.uuid4(), username="manager", email="manager@test.local",
        password_hash="x", role="Manager", is_active=True,
    )
    teams = [Team(id=uuid.uuid4(), name=name, db_name=name, region="EGY") for name in ("Finance", "Sales")]
    session.add_all([user, *teams])
    session.flush()
    session.add_all([
        UserTeamAssignment(
            id=uuid.uuid4(), user_id=user.id, team_id=team.id,
            performance_level="Managerial", access_level="read", assigned_by="Admin",
        )
        for team in teams
    ])
    session.commit()

    scope = get_current_user_scope(
        session,
        SimpleNamespace(state=SimpleNamespace(user={"user_id": str(user.id), "role": "Manager"})),
    )
    assert scope["is_general_manager"] is False
    assert user_can_access_team_level(scope, "Finance", "Managerial") is True
    assert user_can_access_team_level(scope, "Finance", "Corporate") is False
    session.close()
