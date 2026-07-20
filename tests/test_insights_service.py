from datetime import date

import services.insights_service as insights_service_module
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
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
    assert "declined by 81.00 AED" in cpl.explanation
    assert "moving from 55.00 AED to 136.00 AED" in cpl.explanation
    assert "76.00 AED above target" in cpl.explanation
    assert cpl.detail.recommended_focus == "Reduce CPL and review the affected employees with the largest gap."
    assert workspace.performance_drivers[0].impact_points == -5.6
    assert any(item.kpi_key == "cpl" for item in workspace.team_analyses)
    assert workspace.summary.critical_issues == 1
    assert workspace.summary.negative_weighted_drivers == 1
    assert workspace.summary.weighted_net_impact == -5.6
    assert workspace.summary.coverage_percent == 100
    assert workspace.team_summaries[0].team == "Marketing"
    assert workspace.team_summaries[0].score_change == -20.1
    assert cpl.planning_context["baseline_value"] == 55
    assert cpl.planning_context["current_value"] == 136
    assert cpl.planning_context["target_value"] == 60
    assert cpl.planning_context["suggested_action"] == cpl.detail.recommended_focus


def test_single_period_planning_context_uses_the_only_measurement_for_baseline_and_current():
    workspace = _service([
        _record("June", 69.9, 136, 60, .044),
    ]).generate_workspace(_scope(), month="June", year=2026)

    cpl = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")

    assert cpl.detail.previous_value is None
    assert cpl.planning_context["baseline_value"] == 136
    assert cpl.planning_context["current_value"] == 136


def test_near_target_high_weight_kpi_is_at_risk_not_critical():
    previous = _record("May", 90, 57.7, 65, .621)
    current = _record("June", 89, 58, 65, .625)
    for record in (previous, current):
        record.kpi_values[0]["direction"] = "higher_better"
        record.kpi_values[0]["weight_applied"] = .7

    workspace = _service([previous, current]).generate_workspace(_scope(), month="June", year=2026)

    cpl = next(item for item in workspace.team_analyses if item.kpi_key == "cpl")
    assert cpl.severity == "risk"
    assert workspace.summary.critical_issues == 0
    assert workspace.summary.positive_weighted_drivers == 1
    assert workspace.summary.weighted_positive_impact == .4
    assert any(evidence.label == "Target achievement" and evidence.value == "89.2%" for evidence in cpl.detail.evidence)


def test_weighted_impact_keeps_percentage_point_values_unscaled():
    service = _service([
        _record("May", 90, 55, 60, 60.0),
        _record("June", 69.9, 136, 60, 50.0),
    ])

    workspace = service.generate_workspace(_scope(), month="June", year=2026)

    cpl = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")
    assert cpl.impact_points == -10.0
    assert workspace.performance_drivers[0].impact_points == -10.0


def test_zero_target_suppresses_percentage_and_surfaces_data_issue():
    record = _record("June", 80, 5, 0, 0)
    record.kpi_values[0]["direction"] = "higher_better"
    service = _service([record])

    workspace = service.generate_workspace(_scope(), month="June", year=2026)

    kpi = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")
    assert "configured target is zero" in kpi.explanation
    assert "no target percentage is reported" in kpi.explanation
    assert any("Zero KPI targets" in item.title for item in workspace.data_issues)
    assert workspace.summary.expected_kpis == 1
    assert workspace.summary.analyzed_kpis == 0
    assert workspace.summary.coverage_percent == 0


def test_current_month_is_excluded_from_default_period_options(monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 17)

    monkeypatch.setattr(insights_service_module, "date", FakeDate)
    service = _service([
        _record("May", 90, 55, 60, .1),
        _record("June", 88, 54, 59, .1),
        _record("July", 87, 53, 58, .1),
    ])

    workspace = service.generate_workspace(_scope())

    assert [period.month for period in workspace.options.periods] == ["June", "May"]
    assert workspace.comparison.current.month == "June"
    assert workspace.comparison.previous.month == "May"


def test_team_options_follow_selected_region():
    records = [
        _record("June", 90, 55, 60, .1),
        _record("June", 88, 54, 59, .1),
    ]
    records[0].team = "Inbound"
    records[0].region = "EGY"
    records[1].team = "Outbound"
    records[1].region = "UAE"

    service = _service(records)

    eg_workspace = service.generate_workspace(_scope(), month="June", year=2026, region="EGY")
    uae_workspace = service.generate_workspace(_scope(), month="June", year=2026, region="UAE")

    assert eg_workspace.options.teams == ["Inbound"]
    assert uae_workspace.options.teams == ["Outbound"]


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


def test_call_center_operational_analyses_are_available_without_score_impact():
    previous = _record("May", 80, 55, 60, .08)
    current = _record("June", 80, 55, 60, .08)
    for record in (previous, current):
        record.team = "Outbound"
        record.raw_data = {"T.AHT": "00:02:30"}
    previous.geo = GeoData(
        bookings=GeoBreakdown(dubai=100),
        attended=GeoBreakdown(dubai=48),
    )
    current.geo = GeoData(
        bookings=GeoBreakdown(dubai=100),
        attended=GeoBreakdown(dubai=49),
    )
    previous.calls = CallsData(total_handled=100, aht_raw="00:03:00")
    current.calls = CallsData(total_handled=100, aht_raw="00:02:00")

    workspace = _service([previous, current]).generate_workspace(_scope(), month="June", year=2026)
    analyses = {item.kpi_key: item for item in workspace.team_analyses}

    no_show = analyses["no_show_rate"]
    assert no_show.detail.current_value == .51
    assert no_show.detail.previous_value == .52
    assert no_show.detail.target_value == .2
    assert no_show.detail.direction == "lower_better"
    assert no_show.impact_points is None
    assert no_show.trend_label == "Improving · Still above target"
    assert "31.0 percentage points above target" in no_show.explanation
    assert "calculated" not in no_show.explanation.casefold()

    aht = analyses["aht"]
    assert aht.detail.current_value == 2
    assert aht.detail.previous_value == 3
    assert aht.detail.target_value == 2.5
    assert aht.severity == "opportunity"
    assert aht.impact_points is None
    assert {option["key"] for option in workspace.options.kpis} >= {"no_show_rate", "aht"}


def test_legacy_call_center_records_resolve_configured_weighted_kpis():
    current = _record("June", 80, 55, 60, .08)
    current.team = "Outbound"
    current.kpi_values = []
    current.raw_data = {
        "A.Attend%": 58,
        "T.Attend%": 55,
        "A.Booking%": 40,
        "T.Booking%": 46,
        "A.QualityScore": 96,
        "T.Quality%": 95,
        "A.Reachability%": 62,
        "T.Reachability%": 75,
    }

    workspace = _service([current]).generate_workspace(_scope(), month="June", year=2026)
    analyses = {item.kpi_key: item for item in workspace.team_analyses}

    assert set(analyses) >= {"Attendance", "Booking", "Quality", "Other"}
    assert any(evidence.value == "0.0%" for evidence in analyses["Quality"].detail.evidence if evidence.label == "Applied KPI weight")
    assert any(evidence.value == "20.0%" for evidence in analyses["Other"].detail.evidence if evidence.label == "Applied KPI weight")
