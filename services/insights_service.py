from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable, List, Dict

from sqlalchemy.orm import Session

from models.insight_schemas import (
    InsightComparison,
    InsightDetail,
    InsightDriver,
    InsightEvidence,
    InsightFilterOptions,
    InsightItem,
    InsightPeriod,
    InsightRisk,
    InsightSummary,
    InsightsWorkspace,
)
from models.schemas import PerformanceRecord
from repositories.base import PerformanceRepository
from services.dashboard_record_service import DashboardRecordService
from services.management_bsc_service import ManagementBSCService
from services.planning_service import PlanningService, MONTH_ORDER
from utils.report_scope import (
    filter_records_by_scope,
    filter_records_by_team_levels,
    user_can_access_team,
    user_can_access_team_level,
)


class InsightAccessError(PermissionError):
    pass


class InsightValidationError(ValueError):
    pass


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _evaluation_value(record: Any, key: str, default: Any = None) -> Any:
    return _value(_value(record, "evaluation", {}), key, default)


def _period(record: Any) -> tuple[int, int] | None:
    year = _value(record, "year")
    month_number = MONTH_ORDER.get(str(_value(record, "month", "")))
    return (int(year), month_number) if year and month_number else None


def _period_schema(period: tuple[int, int] | None) -> InsightPeriod | None:
    if not period:
        return None
    month = next(name for name, number in MONTH_ORDER.items() if number == period[1])
    return InsightPeriod(year=period[0], month=month, key=f"{period[0]}-{period[1]:02d}")


def _stable_id(*parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _average(values: Iterable[Any]) -> float | None:
    measured = [float(value) for value in values if value is not None]
    return mean(measured) if measured else None


def _format_value(value: float | None, unit: str | None) -> str:
    if value is None:
        return "not available"
    normalized_unit = (unit or "").strip()
    display_value = value * 100 if normalized_unit == "%" and abs(value) <= 1 else value
    if normalized_unit == "%":
        return f"{display_value:,.1f}%"
    if normalized_unit:
        return f"{display_value:,.2f} {normalized_unit}"
    return f"{display_value:,.2f}"


class InsightsService:
    """Canonical deterministic insight orchestration over existing PMS records."""

    def __init__(
        self,
        performance_repo: PerformanceRepository,
        planning_service: PlanningService,
        db: Session | None = None,
        record_service: DashboardRecordService | None = None,
    ):
        self.performance_repo = performance_repo
        self.planning_service = planning_service
        self.db = db
        self.record_service = record_service or (DashboardRecordService(db) if db is not None else None)

    def generate_insights(self, month: str, performance_level: str | None = None) -> List[Dict[str, str]]:
        """Preserve the legacy insights contract used by ``/api/performance/insights``."""
        insights: list[dict[str, str]] = []
        all_records = self.performance_repo.get_all()
        if performance_level:
            all_records = [record for record in all_records if record.performance_level == performance_level]
        current = [record for record in all_records if record.month == month]
        if not current:
            return [{"type": "warning", "message": f"No performance records available for {month} to compile insights."}]

        current_order = MONTH_ORDER.get(month, 0)
        previous_month = next((name for name, number in MONTH_ORDER.items() if number == current_order - 1), None)
        previous = [record for record in all_records if record.month == previous_month] if previous_month else []
        for team in sorted({record.team for record in current}):
            current_scores = [record.evaluation.score for record in current if record.team == team]
            previous_scores = [record.evaluation.score for record in previous if record.team == team]
            if current_scores and previous_scores:
                difference = mean(current_scores) - mean(previous_scores)
                if difference > 1:
                    insights.append({"type": "positive", "message": f"{team} team improved by {difference:.1f}% compared to last month."})
                elif difference < -3:
                    insights.append({"type": "warning", "message": f"{team} team performance declined by {abs(difference):.1f}% compared to last month."})

        low_performers = [record for record in current if record.evaluation.score < 70]
        if low_performers:
            attendance_count = sum(
                1 for record in low_performers
                if record.evaluation.root_cause and record.evaluation.root_cause.kpi == "Attend"
            )
            percentage = int(round(attendance_count / len(low_performers) * 100))
            if percentage > 30:
                insights.append({
                    "type": "warning",
                    "message": f"Attendance contributes to {percentage}% of low performer cases.",
                })

        planning = self.planning_service.classify_all(month, performance_level)
        for category, message, insight_type in (
            ("Training Candidate", "employees are recommended for training.", "warning"),
            ("Promotion Candidate", "employees qualify for promotion review.", "positive"),
            ("Attrition Risk", "employees show high attrition risk characteristics.", "warning"),
        ):
            count = len(planning.get(category, []))
            if count:
                insights.append({"type": insight_type, "message": f"{count} {message}"})

        team_quality: dict[str, float] = {}
        for team in sorted({record.team for record in current}):
            quality_scores = []
            for record in (item for item in current if item.team == team):
                quality = record.achievement.quality_ach
                if quality <= 0:
                    quality = float(record.raw_data.get("A.QualityScore", 0) or 0)
                if quality:
                    quality_scores.append(float(quality))
            if quality_scores:
                team_quality[team] = mean(quality_scores)
        if team_quality:
            top_team = max(team_quality, key=team_quality.get)
            insights.append({
                "type": "positive",
                "message": f"{top_team} achieved the highest quality score averaging {team_quality[top_team] * 100:.1f}%.",
            })
        return insights or [{"type": "positive", "message": "All team metrics are performing stable within expectations."}]

    def _authorized_records(self, scope: dict) -> tuple[list[Any], int]:
        if self.record_service is None or self.db is None:
            raise RuntimeError("Insights workspace requires a database session")
        employee_records = self.record_service.list_records()
        management_records = ManagementBSCService(self.db).list_analysis_records()
        records = [*employee_records, *management_records]
        records = filter_records_by_scope(records, scope)
        records = filter_records_by_team_levels(records, scope)
        missing_year = len([record for record in records if _period(record) is None])
        return records, missing_year

    def authorized_records(self, scope: dict) -> tuple[list[Any], int]:
        """Return scope-filtered source records for adjacent workspaces."""
        return self._authorized_records(scope)

    @staticmethod
    def _options(records: list[Any]) -> InsightFilterOptions:
        periods = sorted({_period(record) for record in records if _period(record)}, reverse=True)
        employees: dict[str, dict[str, str]] = {}
        kpis: dict[str, str] = {}
        for record in records:
            employee_id = str(_value(record, "employee_id", ""))
            if employee_id:
                employees[employee_id] = {
                    "id": employee_id,
                    "name": str(_value(record, "employee_name", "")),
                    "team": str(_value(record, "team", "")),
                    "position": str(_value(record, "position", "") or ""),
                    "performance_level": str(_value(record, "performance_level", "")),
                }
            for kpi in _value(record, "kpi_values", []) or []:
                key = str(_value(kpi, "kpi_key", ""))
                if key:
                    kpis[key] = str(_value(kpi, "label", key))
        return InsightFilterOptions(
            periods=[_period_schema(period) for period in periods if _period_schema(period)],
            regions=sorted({str(_value(record, "region")) for record in records if _value(record, "region")}),
            teams=sorted({str(_value(record, "team")) for record in records if _value(record, "team")}),
            performance_levels=sorted({str(_value(record, "performance_level")) for record in records if _value(record, "performance_level")}),
            positions=sorted({str(_value(record, "position")) for record in records if _value(record, "position")}),
            employees=sorted(employees.values(), key=lambda item: (item["name"], item["id"])),
            kpis=[{"key": key, "label": label} for key, label in sorted(kpis.items(), key=lambda item: item[1])],
        )

    @staticmethod
    def _validate_scope(filters: dict[str, Any], scope: dict) -> None:
        team = filters.get("team")
        level = filters.get("performance_level")
        if team and not user_can_access_team(scope, team):
            raise InsightAccessError("The selected team is outside the authorized insights scope")
        if team and level and not user_can_access_team_level(scope, team, level):
            raise InsightAccessError("The selected performance level is outside the authorized insights scope")

    @staticmethod
    def _filter_records(records: list[Any], filters: dict[str, Any]) -> list[Any]:
        mapping = {
            "region": "region",
            "team": "team",
            "performance_level": "performance_level",
            "position": "position",
            "employee_id": "employee_id",
            "status": "status",
        }
        result = records
        for filter_key, record_key in mapping.items():
            selected = filters.get(filter_key)
            if selected:
                result = [record for record in result if str(_value(record, record_key, "")).casefold() == str(selected).casefold()]
        return result

    @staticmethod
    def _make_item(
        *,
        severity: str,
        insight_type: str,
        title: str,
        explanation: str,
        scope_label: str,
        trend_label: str,
        priority_reason: str,
        detail: InsightDetail,
        team: str | None = None,
        level: str | None = None,
        position: str | None = None,
        employee_id: str | None = None,
        kpi_key: str | None = None,
        impact: float | None = None,
    ) -> InsightItem:
        item_id = _stable_id(insight_type, title, team, level, position, employee_id, kpi_key)
        return InsightItem(
            id=item_id,
            severity=severity,
            insight_type=insight_type,
            title=title,
            explanation=explanation,
            scope=scope_label,
            impact_points=round(impact, 2) if impact is not None else None,
            trend_label=trend_label,
            priority_reason=priority_reason,
            team=team,
            performance_level=level,
            position=position,
            employee_id=employee_id,
            kpi_key=kpi_key,
            detail=detail,
            planning_context={
                "source_insight_id": item_id,
                "title": title,
                "team": team,
                "performance_level": level,
                "position": position,
                "employee_id": employee_id,
                "kpi_key": kpi_key,
                "impact_points": round(impact, 2) if impact is not None else None,
            },
        )

    def _score_insights(
        self,
        current: list[Any],
        previous: list[Any],
        current_period: tuple[int, int],
        previous_period: tuple[int, int] | None,
    ) -> list[InsightItem]:
        items: list[InsightItem] = []
        current_groups: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
        previous_groups: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
        for record in current:
            current_groups[(str(_value(record, "team", "")), str(_value(record, "position", "") or "All positions"), str(_value(record, "performance_level", "")))].append(record)
        for record in previous:
            previous_groups[(str(_value(record, "team", "")), str(_value(record, "position", "") or "All positions"), str(_value(record, "performance_level", "")))].append(record)

        for group, group_records in sorted(current_groups.items()):
            team, position, level = group
            current_score = _average(_evaluation_value(record, "score") for record in group_records)
            previous_score = _average(_evaluation_value(record, "score") for record in previous_groups.get(group, []))
            if current_score is None or previous_score is None:
                continue
            delta = current_score - previous_score
            if abs(delta) < 3:
                continue
            positive = delta > 0
            severity = "opportunity" if positive else ("critical" if delta <= -10 else "risk")
            title = f"{position} average {'improved' if positive else 'declined'} by {abs(delta):.1f}%"
            explanation = (
                f"Average score moved from {previous_score:.1f} to {current_score:.1f} across "
                f"{len(group_records)} measured record{'s' if len(group_records) != 1 else ''}."
            )
            items.append(self._make_item(
                severity=severity,
                insight_type="opportunity" if positive else "performance",
                title=title,
                explanation=explanation,
                scope_label=f"{team} · {position}",
                trend_label=f"vs {_period_schema(previous_period).month} {_period_schema(previous_period).year}" if previous_period else "No comparison",
                priority_reason=f"Overall score movement is {abs(delta):.1f}%.",
                team=team,
                level=level,
                position=None if position == "All positions" else position,
                impact=delta,
                detail=InsightDetail(
                    current_value=current_score,
                    previous_value=previous_score,
                    unit="%",
                    impact_points=delta,
                    affected_teams=[team],
                    affected_positions=[] if position == "All positions" else [position],
                    evidence=[
                        InsightEvidence(label="Current average score", value=f"{current_score:.1f}"),
                        InsightEvidence(label="Previous average score", value=f"{previous_score:.1f}"),
                        InsightEvidence(label="Measured records", value=str(len(group_records))),
                    ],
                    recommended_focus="Review the largest KPI contribution movements in this same scope before selecting an intervention.",
                ),
            ))
        return items

    def _kpi_insights(self, current: list[Any], previous: list[Any]) -> tuple[list[InsightItem], list[InsightDriver], set[tuple[str, str]]]:
        buckets: dict[tuple[str, str, str, str], list[Any]] = defaultdict(list)
        previous_buckets: dict[tuple[str, str, str, str], list[Any]] = defaultdict(list)
        metadata: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for target, records in ((buckets, current), (previous_buckets, previous)):
            for record in records:
                team = str(_value(record, "team", ""))
                position = str(_value(record, "position", "") or "All positions")
                level = str(_value(record, "performance_level", ""))
                for kpi in _value(record, "kpi_values", []) or []:
                    key = str(_value(kpi, "kpi_key", ""))
                    if not key:
                        continue
                    bucket_key = (team, position, level, key)
                    target[bucket_key].append(kpi)
                    metadata[bucket_key] = {
                        "label": str(_value(kpi, "label", key)),
                        "direction": _value(kpi, "direction"),
                        "unit": _value(kpi, "unit"),
                    }

        items: list[InsightItem] = []
        drivers: list[InsightDriver] = []
        high_weight_misses: set[tuple[str, str]] = set()
        for bucket_key, values in sorted(buckets.items()):
            team, position, level, key = bucket_key
            previous_values = previous_buckets.get(bucket_key, [])
            meta = metadata[bucket_key]
            label, direction, unit = meta["label"], meta["direction"], meta["unit"]
            actual = _average(_value(value, "actual_value") for value in values)
            previous_actual = _average(_value(value, "actual_value") for value in previous_values)
            target = _average(_value(value, "target_value") for value in values)
            contribution = _average(_value(value, "contribution") for value in values)
            previous_contribution = _average(_value(value, "contribution") for value in previous_values)
            weight = _average(_value(value, "weight_applied") for value in values)
            if contribution is None or weight is None:
                continue
            gap_points = max(weight - contribution, 0) * 100
            impact = (contribution - previous_contribution) * 100 if previous_contribution is not None else -gap_points
            target_missed = bool(
                actual is not None and target is not None and direction in {"higher_better", "lower_better"}
                and ((direction == "higher_better" and actual < target) or (direction == "lower_better" and actual > target))
            )
            exceeds_target = bool(
                actual is not None and target is not None and direction in {"higher_better", "lower_better"}
                and ((direction == "higher_better" and actual > target) or (direction == "lower_better" and actual < target))
            )
            movement_positive = None
            if actual is not None and previous_actual is not None and direction in {"higher_better", "lower_better"}:
                movement_positive = (actual > previous_actual) if direction == "higher_better" else (actual < previous_actual)

            relevant = abs(impact) >= 1 or (weight >= .15 and target_missed) or exceeds_target
            if not relevant:
                continue
            is_positive = impact > 0 or (exceeds_target and impact >= 0)
            severity = "opportunity" if is_positive else ("critical" if impact <= -5 or (weight >= .2 and target_missed) else "risk")
            if target_missed and weight >= .15:
                high_weight_misses.add((team, key))

            movement_text = "Previous-period value is unavailable."
            if actual is not None and previous_actual is not None:
                verb = "increased" if actual > previous_actual else "decreased" if actual < previous_actual else "remained unchanged"
                interpretation = "positive" if movement_positive else "negative" if movement_positive is False else "neutral"
                movement_text = (
                    f"{label} {verb} from {_format_value(previous_actual, unit)} to {_format_value(actual, unit)}; "
                    f"for a {str(direction).replace('_', ' ')} KPI, this is a {interpretation} movement."
                )
            target_text = "Target is unavailable."
            if target is not None and actual is not None:
                exact_gap = abs(actual - target)
                if target == 0:
                    target_text = f"The configured target is zero; the exact absolute gap is {_format_value(exact_gap, unit)} and no target percentage is reported."
                elif target_missed:
                    target_text = f"It missed the target of {_format_value(target, unit)} by {_format_value(exact_gap, unit)}."
                else:
                    target_text = f"It met or exceeded the target of {_format_value(target, unit)} by {_format_value(exact_gap, unit)}."
            impact_text = (
                f"Its weighted contribution moved the overall score by {impact:+.1f}% versus the comparison period."
                if previous_contribution is not None
                else f"It accounts for approximately {gap_points:.1f}% of the current overall score gap."
            )
            title = (
                f"{label} is a positive score driver" if is_positive
                else f"{label} contributed to the performance gap"
            )
            item = self._make_item(
                severity=severity,
                insight_type="opportunity" if is_positive else "kpi_driver",
                title=title,
                explanation=f"{movement_text} {target_text} {impact_text}",
                scope_label=f"{team} · {position}",
                trend_label="Compared with previous available period" if previous_values else "Current-period gap",
                priority_reason=(
                    f"Weighted contribution changed the overall score by {abs(impact):.1f}%."
                    if previous_contribution is not None
                    else f"Current overall score gap is {gap_points:.1f}%."
                ),
                team=team,
                level=level,
                position=None if position == "All positions" else position,
                kpi_key=key,
                impact=impact,
                detail=InsightDetail(
                    current_value=actual,
                    previous_value=previous_actual,
                    target_value=target,
                    unit=unit,
                    direction=direction,
                    impact_points=impact,
                    affected_teams=[team],
                    affected_positions=[] if position == "All positions" else [position],
                    evidence=[
                        InsightEvidence(label="Current value", value=_format_value(actual, unit)),
                        InsightEvidence(label="Previous value", value=_format_value(previous_actual, unit)),
                        InsightEvidence(label="Target", value=_format_value(target, unit)),
                        InsightEvidence(label="Applied KPI weight", value=f"{weight * 100:.1f}%"),
                        InsightEvidence(label="Measured KPI rows", value=str(len(values))),
                    ],
                    warnings=["Zero targets are not converted into achievement percentages."] if target == 0 else [],
                    recommended_focus="Validate the KPI source values and configuration, then review the affected position or employees in the related dashboard.",
                ),
            )
            items.append(item)
            if abs(impact) >= .5:
                drivers.append(InsightDriver(
                    id=_stable_id("driver", *bucket_key),
                    driver=label,
                    scope=f"{team} · {position}",
                    impact_points=round(impact, 2),
                    direction="positive" if impact > 0 else "negative",
                    insight_id=item.id,
                ))
        return items, drivers, high_weight_misses

    def _employee_risks(self, current: list[Any], previous: list[Any]) -> list[InsightItem]:
        previous_by_employee = {str(_value(record, "employee_id")): record for record in previous}
        items: list[InsightItem] = []
        for record in current:
            employee_id = str(_value(record, "employee_id", ""))
            previous_record = previous_by_employee.get(employee_id)
            current_score = _evaluation_value(record, "score")
            previous_score = _evaluation_value(previous_record, "score") if previous_record else None
            if current_score is None or previous_score is None or float(current_score) >= 70 or float(previous_score) >= 70:
                continue
            team = str(_value(record, "team", ""))
            name = str(_value(record, "employee_name", employee_id))
            items.append(self._make_item(
                severity="critical" if float(current_score) < 50 else "risk",
                insight_type="employee_risk",
                title=f"{name} remained below target for two periods",
                explanation=f"Overall score was {float(previous_score):.1f}% in the comparison period and {float(current_score):.1f}% in the selected period, both below the 70% review threshold.",
                scope_label=f"{team} · {employee_id}",
                trend_label="Two consecutive available periods",
                priority_reason="Repeated below-threshold performance has stronger priority than a single-period miss.",
                team=team,
                level=str(_value(record, "performance_level", "")),
                position=_value(record, "position"),
                employee_id=employee_id,
                impact=float(current_score) - float(previous_score),
                detail=InsightDetail(
                    current_value=float(current_score),
                    previous_value=float(previous_score),
                    target_value=70,
                    unit="%",
                    impact_points=float(current_score) - float(previous_score),
                    affected_teams=[team],
                    affected_positions=[str(_value(record, "position"))] if _value(record, "position") else [],
                    affected_employees=[employee_id],
                    evidence=[
                        InsightEvidence(label="Current score", value=f"{float(current_score):.1f}"),
                        InsightEvidence(label="Previous score", value=f"{float(previous_score):.1f}"),
                    ],
                    recommended_focus="Review the employee KPI breakdown and confirm an appropriate coaching, training or performance-improvement response.",
                ),
            ))
        return items

    def _data_quality_items(
        self,
        records: list[Any],
        current: list[Any],
        previous_period: tuple[int, int] | None,
        missing_year_count: int,
    ) -> list[InsightItem]:
        issues: list[InsightItem] = []

        def add(title: str, explanation: str, count: int, warning: str) -> None:
            issues.append(self._make_item(
                severity="information",
                insight_type="data_quality",
                title=title,
                explanation=explanation,
                scope_label="Authorized data scope",
                trend_label="Data-quality check",
                priority_reason=f"{count} affected record{'s' if count != 1 else ''} require review.",
                detail=InsightDetail(
                    affected_teams=sorted({str(_value(record, "team")) for record in current if _value(record, "team")}),
                    evidence=[InsightEvidence(label="Affected records", value=str(count))],
                    warnings=[warning],
                    recommended_focus="Review the source upload and effective configuration before relying on affected comparisons.",
                ),
            ))

        if missing_year_count:
            add(
                "Records without an explicit year were excluded",
                f"{missing_year_count} authorized legacy records cannot be assigned safely to a reporting period and were not used in period comparisons.",
                missing_year_count,
                "No year was inferred from month-only data.",
            )
        if previous_period is None:
            add(
                "Comparison-period data is unavailable",
                "The selected scope has no earlier explicit period, so period-change claims are suppressed and only current gaps are shown.",
                len(current),
                "Score contribution deltas require a valid previous period.",
            )
        if not current:
            add(
                "Required period data is missing",
                "No performance records exist for the selected period and authorized filter scope.",
                1,
                "No fallback period was substituted for the requested period.",
            )
        zero_targets = sum(
            1 for record in current for kpi in (_value(record, "kpi_values", []) or [])
            if _value(kpi, "target_value") == 0
        )
        if zero_targets:
            add(
                "Zero KPI targets require configuration review",
                f"{zero_targets} measured KPI row{'s have' if zero_targets != 1 else ' has'} a zero target. Exact gaps are retained, but target percentages are suppressed.",
                zero_targets,
                "A zero target can be valid only when explicitly intended by the KPI configuration.",
            )
        missing_direction = sum(
            1 for record in current for kpi in (_value(record, "kpi_values", []) or [])
            if _value(kpi, "direction") not in {"higher_better", "lower_better"}
        )
        if missing_direction:
            add(
                "KPI direction is missing or invalid",
                f"{missing_direction} KPI row{'s cannot' if missing_direction != 1 else ' cannot'} be interpreted safely as positive or negative movement.",
                missing_direction,
                "Direction-dependent narratives were omitted for these rows.",
            )
        record_keys = [
            (str(_value(record, "employee_id")), str(_value(record, "team")), str(_value(record, "performance_level")), _period(record))
            for record in records if _period(record)
        ]
        duplicate_count = sum(count - 1 for count in Counter(record_keys).values() if count > 1)
        if duplicate_count:
            add(
                "Duplicate performance records detected",
                f"{duplicate_count} duplicate employee/team/level/period record{'s were' if duplicate_count != 1 else ' was'} detected in the authorized source data.",
                duplicate_count,
                "Aggregated results may be overstated until source duplicates are resolved.",
            )

        weights_by_scope: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for record in current:
            scope_key = (str(_value(record, "team")), str(_value(record, "position") or ""), str(_value(record, "performance_level")))
            for kpi in _value(record, "kpi_values", []) or []:
                if _value(kpi, "weight_applied") is not None:
                    weights_by_scope[scope_key][str(_value(kpi, "kpi_key"))].append(float(_value(kpi, "weight_applied")))
        invalid_weight_scopes = sum(
            1 for values in weights_by_scope.values()
            if abs(sum(mean(weights) for weights in values.values()) - 1) > .01
        )
        if invalid_weight_scopes:
            add(
                "KPI weights are incomplete",
                f"{invalid_weight_scopes} current team/position scope{'s do' if invalid_weight_scopes != 1 else ' does'} not resolve to a complete 100% KPI weight configuration.",
                invalid_weight_scopes,
                "Overall score interpretation may be partial for the affected scope.",
            )
        return issues

    @staticmethod
    def _sort_items(items: list[InsightItem]) -> list[InsightItem]:
        rank = {"critical": 0, "risk": 1, "opportunity": 2, "information": 3}
        return sorted(items, key=lambda item: (rank[item.severity], -(abs(item.impact_points) if item.impact_points is not None else 0), item.id))

    def generate_workspace(self, scope: dict, **filters: Any) -> InsightsWorkspace:
        self._validate_scope(filters, scope)
        authorized_records, missing_year_count = self._authorized_records(scope)
        options = self._options(authorized_records)
        records = self._filter_records(authorized_records, filters)
        explicit_periods = sorted({_period(record) for record in records if _period(record)})

        requested_period = None
        if filters.get("year") and filters.get("month"):
            month_number = MONTH_ORDER.get(str(filters["month"]))
            if not month_number:
                raise InsightValidationError("Unknown insight month")
            requested_period = (int(filters["year"]), month_number)
        current_period = requested_period or (explicit_periods[-1] if explicit_periods else None)
        if current_period is None:
            data_issues = self._data_quality_items(records, [], None, missing_year_count)
            return InsightsWorkspace(
                summary=InsightSummary(data_issues=len(data_issues)),
                priority_insights=self._sort_items(data_issues),
                performance_drivers=[],
                risks=[InsightRisk(key="data", label="Missing or incomplete data", count=max(missing_year_count, 1), explanation="No explicit reporting period is available in the authorized scope.", filter_type="data_quality")],
                opportunities=[],
                data_issues=data_issues,
                options=options,
                comparison=InsightComparison(note="No explicit reporting period is available."),
                deferred_capabilities=["Overdue corrective actions require a persisted due date, which is not available in the current action model."],
            )

        previous_candidates = [period for period in explicit_periods if period < current_period]
        previous_period = previous_candidates[-1] if previous_candidates else None
        current = [record for record in records if _period(record) == current_period]
        previous = [record for record in records if previous_period and _period(record) == previous_period]

        items = self._score_insights(current, previous, current_period, previous_period)
        kpi_items, drivers, high_weight_misses = self._kpi_insights(current, previous)
        employee_items = self._employee_risks(current, previous)
        planning_records = [record for record in records if isinstance(record, PerformanceRecord)]
        planning = self.planning_service.classify_records(
            planning_records,
            month=_period_schema(current_period).month,
            year=current_period[0],
        )
        classifications_by_employee: dict[str, list[str]] = defaultdict(list)
        for category, category_records in planning.items():
            for record in category_records:
                classifications_by_employee[str(record.employee_id)].append(category)
        for item in employee_items:
            categories = sorted(classifications_by_employee.get(str(item.employee_id), []))
            if categories:
                item.planning_context["existing_classifications"] = ", ".join(categories)
        data_issues = self._data_quality_items(records, current, previous_period, missing_year_count)
        items.extend(kpi_items)
        items.extend(employee_items)
        items.extend(data_issues)
        for item in items:
            item.planning_context["period"] = f"{_period_schema(current_period).month} {current_period[0]}"

        selected_kpi = filters.get("kpi")
        selected_severity = filters.get("severity")
        selected_type = filters.get("insight_type")
        selected_status = filters.get("insight_status")
        filtered_items = [
            item for item in items
            if (not selected_kpi or item.kpi_key == selected_kpi)
            and (not selected_severity or item.severity == selected_severity)
            and (not selected_type or item.insight_type == selected_type)
            and (not selected_status or item.status == selected_status)
        ]
        sorted_items = self._sort_items(filtered_items)
        priority_items = sorted_items[:50]
        item_ids = {item.id for item in priority_items}
        drivers = sorted(
            [driver for driver in drivers if driver.insight_id in item_ids],
            key=lambda driver: (-abs(driver.impact_points), driver.id),
        )[:10]
        opportunities = [item for item in sorted_items if item.severity == "opportunity"]
        visible_data_issues = [item for item in sorted_items if item.insight_type == "data_quality"]
        summary = InsightSummary(
            critical=sum(item.severity == "critical" for item in sorted_items),
            at_risk=sum(item.severity == "risk" for item in sorted_items),
            opportunities=len(opportunities),
            data_issues=len(visible_data_issues),
        )

        repeated_employees = {item.employee_id for item in employee_items if item.employee_id}
        declining_teams = {
            item.team for item in items
            if item.insight_type == "performance" and item.impact_points is not None and item.impact_points < 0 and item.team
        }
        risk_cards = [
            InsightRisk(key="teams", label="Declining teams", count=len(declining_teams), explanation="Teams with a material score decline in the latest available comparison.", filter_type="performance"),
            InsightRisk(key="employees", label="Repeatedly below target", count=len(repeated_employees), explanation="Employees below the 70% review threshold for two available periods.", filter_type="employee_risk"),
            InsightRisk(key="kpis", label="High-weight KPI risks", count=len(high_weight_misses), explanation="High-weight KPIs that currently miss their configured target.", filter_type="kpi_driver"),
            InsightRisk(key="data", label="Data or configuration issues", count=len(data_issues), explanation="Detected source, period or KPI configuration issues.", filter_type="data_quality"),
        ]

        current_schema = _period_schema(current_period)
        previous_schema = _period_schema(previous_period)
        adjacent = bool(previous_period and (
            (previous_period[0] == current_period[0] and previous_period[1] == current_period[1] - 1)
            or (previous_period == (current_period[0] - 1, 12) and current_period[1] == 1)
        ))
        comparison_note = None
        if previous_period is None:
            comparison_note = "No earlier explicit period is available in the selected scope."
        elif not adjacent:
            comparison_note = "Comparison uses the nearest earlier available period; intermediate period data is missing."

        return InsightsWorkspace(
            summary=summary,
            priority_insights=priority_items,
            performance_drivers=drivers,
            risks=risk_cards,
            opportunities=opportunities,
            data_issues=visible_data_issues,
            options=options,
            comparison=InsightComparison(current=current_schema, previous=previous_schema, is_adjacent=adjacent, note=comparison_note),
            deferred_capabilities=["Overdue corrective actions require a persisted due date, which is not available in the current action model."],
        )
