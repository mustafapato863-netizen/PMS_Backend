import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import Team, User
from models.planning_schemas import PlanCreate, PlanUpdate
from services.planning_service import PlanningService, PlanningValidationError


class StubRepo:
    def get_all(self): return []


@pytest.fixture()
def workspace():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    team = Team(id=uuid.uuid4(), name="Marketing", db_name="marketing", display_name="Marketing", region="EGY", team_level="employee", is_active=True)
    user = User(id=uuid.uuid4(), username="manager", email="manager@example.com", password_hash="x", role="Manager", is_active=True)
    db.add_all([team, user]); db.commit()
    scope = {"user_id": str(user.id), "role": "Admin", "is_general_manager": True, "legacy_unscoped": False, "accessible_teams": ["Marketing"], "accessible_team_levels": [("Marketing", "Employee")]}
    yield db, user, scope
    db.close()


def _payload(user, **changes):
    start = date.today() - timedelta(days=10)
    values = dict(
        name="Improve Marketing Performance", scope_type="Team", team="Marketing", performance_level="Employee",
        period_start=start, period_end=start + timedelta(days=60), due_date=start + timedelta(days=60), owner_user_id=user.id,
        baseline_value=60, target_value=80, current_value=70, expected_impact=20, no_insight_reason="Operational review requested",
        objectives=[{"name": "Raise team score", "measurement_type": "score", "baseline_value": 60, "target_value": 80, "current_value": 70, "unit": "%", "direction": "higher_better", "due_date": start + timedelta(days=60), "owner_user_id": user.id, "linked_kpi_keys": ["quality"]}],
        kpis=[{"kpi_key": "quality", "kpi_label": "Quality", "unit": "%", "direction": "higher_better", "baseline_value": 60, "target_value": 80, "current_value": 70}],
        actions=[{"title": "Coaching", "description": "Run weekly coaching sessions", "owner_user_id": user.id, "due_date": date.today() - timedelta(days=1), "priority": "High", "objective_index": 0, "linked_kpi_key": "quality"}],
        milestones=[{"name": "First review", "due_date": start + timedelta(days=20), "owner_user_id": user.id}], activate=True,
    )
    values.update(changes); return PlanCreate(**values)


def test_create_persists_normalized_plan_and_reuses_action_table(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user), scope)
    detail = service.get(str(plan.id), scope)

    assert detail["stored_status"] == "In Progress"
    assert detail["progress"]["overall"] == 25.0
    assert detail["counts"] == {"objectives": 1, "actions": 1, "kpis": 1, "milestones": 1, "notes": 0}
    assert detail["actions"][0]["linked_kpi"] == "quality"
    assert any("overdue" in reason for reason in detail["risk_reasons"])
    assert detail["status"] == "At Risk"


def test_draft_requires_explicit_activation(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)
    assert service.get(str(plan.id), scope)["status"] == "Draft"


def test_invalid_objective_kpi_rolls_back_entire_plan(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    payload = _payload(user, kpis=[])
    with pytest.raises(PlanningValidationError, match="unknown KPI"):
        service.create(payload, scope)
    assert service.plans.list_active() == []


def test_manual_at_risk_and_completion_are_explainable(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)
    with pytest.raises(PlanningValidationError, match="requires a reason"):
        service.update(str(plan.id), PlanUpdate(status="At Risk"), scope)
    with pytest.raises(PlanningValidationError, match="Completion requires"):
        service.update(str(plan.id), PlanUpdate(status="Completed", completion_note="Done"), scope)
