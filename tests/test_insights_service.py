from models.schemas import EvaluationData, PerformanceRecord
from services.insights_service import InsightAccessError, InsightsService
from services.planning_service import PlanningService


class StubRepository:
    def __init__(self, records):
        self.records = records

    def get_all(self):
        return self.records


def _record(month: str, score: float, actual: float, target: float, contribution: float) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"E1_2026_{month}",
        employee_id="E1",
        employee_name="Analyst One",
        team="Marketing",
        month=month,
        year=2026,
        region="EGY",
        position="Media Buyer",
        performance_level="Employee",
        status="Below",
        evaluation=EvaluationData(score=score, grade="C"),
        kpi_values=[{
            "kpi_key": "cpl",
            "label": "CPL",
            "direction": "lower_better",
            "unit": "AED",
            "actual_value": actual,
            "target_value": target,
            "weight_applied": .1,
            "contribution": contribution,
        }],
    )


def _service(records):
    repository = StubRepository(records)
    service = InsightsService(repository, PlanningService(repository))
    service._authorized_records = lambda _scope: (records, 0)
    return service


def _scope():
    return {
        "role": "Admin",
        "is_general_manager": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }


def test_lower_better_kpi_narrative_uses_real_values_and_weighted_impact():
    service = _service([
        _record("May", 90, 55, 60, .1),
        _record("June", 69.9, 136, 60, .044),
    ])

    workspace = service.generate_workspace(_scope(), month="June", year=2026)

    cpl = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")
    assert cpl.impact_points == -5.6
    assert "increased from 55.00 AED to 136.00 AED" in cpl.explanation
    assert "lower better KPI, this is a negative movement" in cpl.explanation
    assert "missed the target of 60.00 AED by 76.00 AED" in cpl.explanation
    assert workspace.performance_drivers[0].impact_points == -5.6


def test_zero_target_suppresses_percentage_and_surfaces_data_issue():
    record = _record("June", 80, 5, 0, 0)
    record.kpi_values[0]["direction"] = "higher_better"
    service = _service([record])

    workspace = service.generate_workspace(_scope(), month="June", year=2026)

    kpi = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")
    assert "configured target is zero" in kpi.explanation
    assert "no target percentage is reported" in kpi.explanation
    assert any("Zero KPI targets" in item.title for item in workspace.data_issues)


def test_missing_requested_period_does_not_fallback_and_order_is_deterministic():
    service = _service([_record("May", 90, 55, 60, .1)])

    first = service.generate_workspace(_scope(), month="June", year=2026)
    second = service.generate_workspace(_scope(), month="June", year=2026)

    assert first.comparison.current.month == "June"
    assert any(item.title == "Required period data is missing" for item in first.data_issues)
    assert [item.id for item in first.priority_insights] == [item.id for item in second.priority_insights]


def test_selected_team_outside_scope_is_rejected():
    service = _service([_record("June", 80, 55, 60, .08)])
    manager_scope = _scope() | {
        "role": "Manager",
        "is_general_manager": False,
        "accessible_teams": ["Sales"],
    }

    try:
        service.generate_workspace(manager_scope, team="Marketing")
    except InsightAccessError:
        pass
    else:
        raise AssertionError("Expected the unauthorized team filter to be rejected")
