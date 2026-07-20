from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from statistics import mean
from typing import Any, Iterable, List, Dict

from sqlalchemy.orm import Session

from config.loader import ConfigurationError, find_team_config_by_db_name, load_team_config, resolve_team_config
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
    InsightTeamSummary,
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


def _nested_value(record: Any, parent: str, key: str, default: Any = None) -> Any:
    return _value(_value(record, parent, {}), key, default)


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


def _target_achievement(actual: float | None, target: float | None, direction: str | None) -> float | None:
    """Return an uncapped target-achievement ratio for severity decisions."""
    if actual is None or target is None or target <= 0 or direction not in {"higher_better", "lower_better"}:
        return None
    if direction == "lower_better":
        return 1.0 if actual <= 0 else target / actual
    return actual / target


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


def _format_gap(value: float, unit: str | None) -> str:
    if (unit or "").strip() == "%" and abs(value) <= 1:
        return f"{value * 100:,.1f} percentage points"
    return _format_value(value, unit)


def _geo_total(record: Any, field: str) -> float:
    breakdown = _nested_value(record, "geo", field, {})
    return sum(float(_value(breakdown, key, 0) or 0) for key in ("dubai", "sharjah", "ajman", "clinics"))


def _aht_minutes(value: Any) -> float:
    if isinstance(value, str) and ":" in value:
        parts = [float(part or 0) for part in value.split(":")]
        parts = ([0.0] * (3 - len(parts))) + parts
        return parts[-3] * 60 + parts[-2] + parts[-1] / 60
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if numeric <= 0:
        return 0.0
    if numeric < 1:
        return numeric * 24 * 60
    if numeric > 10:
        return numeric / 60
    return numeric


@lru_cache(maxsize=64)
def _analysis_config(team: str, level: str, position: str) -> dict[str, Any] | None:
    try:
        try:
            base = load_team_config(team)
        except ConfigurationError:
            base = find_team_config_by_db_name(team)
            if not base:
                return None
        return resolve_team_config(base, level or "Employee", position or None)
    except ConfigurationError:
        return None


def _configured_kpi_values(record: Any) -> list[Any]:
    persisted = list(_value(record, "kpi_values", []) or [])
    team = str(_value(record, "team", ""))
    level = str(_value(record, "performance_level", "Employee") or "Employee")
    position = str(_value(record, "position", "") or "")
    config = _analysis_config(team, level, position)
    if persisted:
        if not config:
            return persisted
        metadata = {}
        for kpi in config.get("kpis", []) or []:
            for identity in (kpi.get("key"), kpi.get("label")):
                if identity:
                    metadata[str(identity).casefold()] = kpi
        enriched = []
        for value in persisted:
            key = str(_value(value, "kpi_key", ""))
            kpi = metadata.get(key.casefold(), {})
            if not kpi:
                # Persisted evidence is retained on the record, but unknown/stale
                # keys are not interpreted as scored KPIs for this applied config.
                continue
            if isinstance(value, dict):
                item = dict(value)
            else:
                item = {
                    "kpi_key": key,
                    "actual_value": _value(value, "actual_value"),
                    "target_value": _value(value, "target_value"),
                    "achievement_ratio": _value(value, "achievement_ratio"),
                    "weight_applied": _value(value, "weight_applied"),
                    "contribution": _value(value, "contribution"),
                }
            item.setdefault("label", kpi.get("label") or key)
            item.setdefault("direction", kpi.get("direction") or "higher_better")
            item.setdefault("unit", kpi.get("unit") or "number")
            enriched.append(item)
        return enriched
    if not config:
        return []
    raw_data = _value(record, "raw_data", {}) or {}
    actuals = _value(record, "actual", {}) or {}
    fallback_actuals = {
        "attendance": _value(actuals, "attend_rate"),
        "attend": _value(actuals, "attend_rate"),
        "booking": _value(actuals, "booking_rate"),
        "quality": _value(actuals, "quality_rate"),
        "reachability": _value(actuals, "reachability_rate"),
        "abandon": _value(actuals, "abandon_rate"),
        "utz": _value(actuals, "utz_rate"),
        "utilization": _value(actuals, "utz_rate"),
        "rejection": _value(actuals, "rejection_rate"),
        "initialerror": _value(actuals, "initial_error_rate"),
        "submission": _value(actuals, "submission_rate"),
    }
    values: list[dict[str, Any]] = []
    for kpi in config.get("kpis", []) or []:
        key = str(kpi.get("key") or kpi.get("label") or "")
        label = str(kpi.get("label") or key)
        unit = str(kpi.get("unit") or "number")
        direction = str(kpi.get("direction") or "higher_better")
        raw_actual = _value(raw_data, str(kpi.get("actual_col") or ""))
        raw_target = _value(raw_data, str(kpi.get("target_col") or ""))
        normalized_key = "".join(character for character in f"{key}{label}".casefold() if character.isalnum())
        if raw_actual in (None, ""):
            raw_actual = next((value for name, value in fallback_actuals.items() if name in normalized_key and value is not None), None)
        if "aht" in normalized_key or "handletime" in normalized_key:
            actual = _aht_minutes(raw_actual or _nested_value(record, "calls", "aht_raw"))
            target = _aht_minutes(raw_target)
            unit = "min"
        else:
            try:
                actual = float(raw_actual)
                target = float(raw_target)
            except (TypeError, ValueError):
                continue
            if unit == "%":
                actual = actual / 100 if abs(actual) > 1 else actual
                target = target / 100 if abs(target) > 1 else target
        if target <= 0:
            achievement = 0.0
        elif direction == "lower_better":
            achievement = target / max(actual, .0001)
        else:
            achievement = actual / target
        weight = float(kpi.get("weight") or 0)
        if weight > 1:
            weight /= 100
        if str(_value(record, "month", "")).casefold() == "june" and int(_value(record, "year", 0) or 0) == 2026:
            if team == "Inbound" and "quality" in normalized_key:
                weight = 0.0
            elif team == "Inbound" and any(name in normalized_key for name in ("utz", "utilization", "abandon")):
                weight = .15
            elif team == "Outbound" and "quality" in normalized_key:
                weight = 0.0
            elif team == "Outbound" and "reachability" in normalized_key:
                weight = .2
        values.append({
            "kpi_key": key,
            "label": label,
            "direction": direction,
            "unit": unit,
            "actual_value": actual,
            "target_value": target,
            "weight_applied": weight,
            "contribution": min(max(achievement, 0), 1) * weight,
        })
    return values


def _analysis_narrative(
    label: str,
    actual: float | None,
    previous: float | None,
    target: float | None,
    unit: str | None,
    direction: str | None,
) -> tuple[str, bool | None, bool, bool]:
    valid_direction = direction in {"higher_better", "lower_better"}
    movement_positive: bool | None = None
    movement_text = "Previous-period value is unavailable."
    if actual is not None and previous is not None and valid_direction:
        movement_positive = actual > previous if direction == "higher_better" else actual < previous
        movement_delta = abs(actual - previous)
        relative_delta = abs((actual - previous) / previous) * 100 if previous else None
        movement_word = "improved" if movement_positive else "declined" if actual != previous else "remained stable"
        movement_suffix = ""
        if relative_delta is not None and actual != previous:
            movement_noun = "improvement" if movement_positive else "decline"
            movement_suffix = f" ({relative_delta:.1f}% {movement_noun})"
        movement_text = (
            f"{label} {movement_word} by {_format_gap(movement_delta, unit)}, moving from "
            f"{_format_value(previous, unit)} to {_format_value(actual, unit)}"
            f"{movement_suffix}."
        )

    target_missed = bool(
        actual is not None and target is not None and valid_direction
        and ((direction == "higher_better" and actual < target) or (direction == "lower_better" and actual > target))
    )
    target_exceeded = bool(
        actual is not None and target is not None and valid_direction
        and ((direction == "higher_better" and actual >= target) or (direction == "lower_better" and actual <= target))
    )
    target_text = "Target is unavailable."
    if actual is not None and target is not None:
        exact_gap = abs(actual - target)
        target_name = "maximum allowed" if direction == "lower_better" else "target"
        if target == 0:
            target_text = f"The configured target is zero; the exact absolute gap is {_format_value(exact_gap, unit)} and no target percentage is reported."
        elif target_missed:
            relation = "above" if direction == "lower_better" else "below"
            target_text = (
                f"Current is {_format_value(actual, unit)} and the {target_name} is {_format_value(target, unit)}. "
                f"The result remains {_format_gap(exact_gap, unit)} {relation} target, so further improvement is required."
            )
        else:
            target_text = (
                f"Current is {_format_value(actual, unit)} and the {target_name} is {_format_value(target, unit)}. "
                f"The target was achieved by {_format_gap(exact_gap, unit)}."
            )
    return f"{movement_text} {target_text}", movement_positive, target_missed, target_exceeded


def _kpi_recommended_focus(label: str, direction: str | None, *, target_missed: bool) -> str:
    if target_missed:
        verb = "Reduce" if direction == "lower_better" else "Increase" if direction == "higher_better" else "Improve"
        return f"{verb} {label} and review the affected employees with the largest gap."
    return f"Maintain {label} performance and monitor the next-period movement."


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
        employee_records = self.record_service.list_analysis_records()
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
    def _options(records: list[Any], filters: dict[str, Any] | None = None) -> InsightFilterOptions:
        today = date.today()
        selected_region = str((filters or {}).get("region") or "").casefold()
        region_records = [
            record for record in records
            if not selected_region or str(_value(record, "region", "")).casefold() == selected_region
        ]
        completed_periods = [
            period for period in sorted({_period(record) for record in records if _period(record)}, reverse=True)
            if period < (today.year, today.month)
        ]
        periods = completed_periods
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
            for kpi in _configured_kpi_values(record):
                key = str(_value(kpi, "kpi_key", ""))
                if key:
                    kpis[key] = str(_value(kpi, "label", key))
            team = str(_value(record, "team", ""))
            if team in {"Inbound", "Outbound", "Inbound UAE"}:
                kpis["no_show_rate"] = "No Show Rate"
            if team == "Outbound":
                kpis["aht"] = "AHT (Handle Time)"
        return InsightFilterOptions(
            periods=[_period_schema(period) for period in periods if _period_schema(period)],
            regions=sorted({str(_value(record, "region")) for record in records if _value(record, "region")}),
            teams=sorted({str(_value(record, "team")) for record in region_records if _value(record, "team")}),
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
        included_in_score: bool = True,
        weight: float | None = None,
        evidence_classification: str | None = None,
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
            included_in_score=included_in_score,
            weight=weight,
            evidence_classification=evidence_classification,
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
                "baseline_value": detail.previous_value if detail.previous_value is not None else detail.current_value,
                "current_value": detail.current_value,
                "target_value": detail.target_value,
                "unit": detail.unit,
                "direction": detail.direction,
                "suggested_action": detail.recommended_focus,
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

    def _operational_kpi_insights(self, current: list[Any], previous: list[Any]) -> list[InsightItem]:
        current_groups: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
        previous_groups: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
        for target, records in ((current_groups, current), (previous_groups, previous)):
            for record in records:
                team = str(_value(record, "team", ""))
                if team not in {"Inbound", "Outbound", "Inbound UAE"}:
                    continue
                target[(
                    team,
                    str(_value(record, "position", "") or "All positions"),
                    str(_value(record, "performance_level", "")),
                )].append(record)

        def no_show(records: list[Any]) -> float | None:
            bookings = sum(_geo_total(record, "bookings") for record in records)
            attended = sum(_geo_total(record, "attended") for record in records)
            return (bookings - attended) / bookings if bookings > 0 else None

        def aht(records: list[Any]) -> tuple[float | None, float | None]:
            weighted_total = 0.0
            handled_total = 0.0
            unweighted: list[float] = []
            targets: list[float] = []
            for record in records:
                actual = _aht_minutes(_nested_value(record, "calls", "aht_raw"))
                handled = float(_nested_value(record, "calls", "total_handled", 0) or 0)
                if actual > 0:
                    weighted_total += actual * handled
                    handled_total += handled
                    unweighted.append(actual)
                raw_data = _value(record, "raw_data", {}) or {}
                target = _aht_minutes(
                    _value(raw_data, "T.AHT")
                    or _value(raw_data, "T.AHTTarget")
                    or _value(raw_data, "T.AHT_Target")
                )
                if target > 0:
                    targets.append(target)
            actual_value = weighted_total / handled_total if handled_total > 0 else (_average(unweighted) if unweighted else None)
            return actual_value, (_average(targets) if targets else None)

        items: list[InsightItem] = []
        for group, group_records in sorted(current_groups.items()):
            team, position, level = group
            previous_records = previous_groups.get(group, [])
            existing_kpis = {
                str(_value(kpi, "kpi_key", "")).casefold()
                for record in group_records
                for kpi in (_value(record, "kpi_values", []) or [])
            }
            existing_labels = {
                str(_value(kpi, "label", "")).casefold()
                for record in group_records
                for kpi in (_value(record, "kpi_values", []) or [])
            }
            metrics: list[tuple[str, str, float | None, float | None, float | None, str, str]] = []
            if not any("no_show" in key for key in existing_kpis) and not any("no show" in label for label in existing_labels):
                metrics.append(("no_show_rate", "No Show Rate", no_show(group_records), no_show(previous_records), .2, "%", "lower_better"))
            has_aht = any("aht" in key for key in existing_kpis) or any("aht" in label or "handle time" in label for label in existing_labels)
            if team == "Outbound" and not has_aht:
                current_aht, target_aht = aht(group_records)
                previous_aht, _ = aht(previous_records)
                metrics.append(("aht", "AHT (Handle Time)", current_aht, previous_aht, target_aht, "min", "lower_better"))

            for key, label, actual, previous_actual, target, unit, direction in metrics:
                if actual is None or target is None:
                    continue
                narrative, movement_positive, target_missed, target_met = _analysis_narrative(
                    label, actual, previous_actual, target, unit, direction
                )
                achievement = (1.0 if actual <= 0 else target / actual) if direction == "lower_better" else actual / target
                severity = "opportunity" if target_met else ("critical" if achievement < .8 else "risk")
                relation = "above" if direction == "lower_better" else "below"
                if movement_positive and target_missed:
                    title = f"{label} is improving but remains {relation} target"
                    trend_label = f"Improving · Still {relation} target"
                elif target_missed:
                    title = f"{label} remains {relation} target"
                    trend_label = "Target gap requires attention"
                else:
                    title = f"{label} is on target"
                    trend_label = "Target achieved"
                items.append(self._make_item(
                    severity=severity,
                    insight_type="opportunity" if target_met else "kpi_driver",
                    title=title,
                    explanation=narrative,
                    scope_label=f"{team} · {position}",
                    trend_label=trend_label,
                    priority_reason="This operational KPI supports diagnosis but does not contribute to the weighted score for this period.",
                    team=team,
                    level=level,
                    position=None if position == "All positions" else position,
                    kpi_key=key,
                    included_in_score=False,
                    weight=0.0,
                    evidence_classification="Operational diagnostic — not included in PMS score",
                    detail=InsightDetail(
                        current_value=actual,
                        previous_value=previous_actual,
                        target_value=target,
                        unit=unit,
                        direction=direction,
                        affected_teams=[team],
                        affected_positions=[] if position == "All positions" else [position],
                        evidence=[
                            InsightEvidence(label="Current value", value=_format_value(actual, unit)),
                            InsightEvidence(label="Previous value", value=_format_value(previous_actual, unit)),
                            InsightEvidence(label="Target", value=_format_value(target, unit)),
                            InsightEvidence(label="Measured records", value=str(len(group_records))),
                            InsightEvidence(label="Weight", value="0%"),
                            InsightEvidence(label="Included in final score", value="No"),
                        ],
                        recommended_focus=_kpi_recommended_focus(label, direction, target_missed=target_missed),
                    ),
                ))
        return items

    def _kpi_insights(self, current: list[Any], previous: list[Any]) -> tuple[list[InsightItem], list[InsightItem], list[InsightDriver], set[tuple[str, str]]]:
        buckets: dict[tuple[str, str, str, str], list[Any]] = defaultdict(list)
        previous_buckets: dict[tuple[str, str, str, str], list[Any]] = defaultdict(list)
        metadata: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for target, records in ((buckets, current), (previous_buckets, previous)):
            for record in records:
                team = str(_value(record, "team", ""))
                position = str(_value(record, "position", "") or "All positions")
                level = str(_value(record, "performance_level", ""))
                for kpi in _configured_kpi_values(record):
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
        analyses: list[InsightItem] = []
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
            if target is None or target == 0:
                configuration_item = self._make_item(
                    severity="information",
                    insight_type="data_quality",
                    title=f"{label} configuration requires review",
                    explanation="The configured target is zero, so no target percentage is reported. It cannot be interpreted as achieved or failed and is excluded from weighted gap analysis.",
                    scope_label=f"{team} · {position}",
                    trend_label="Configuration requires review",
                    priority_reason="No achievement, lost-points or projected-impact calculation is valid without a non-zero target.",
                    team=team,
                    level=level,
                    position=None if position == "All positions" else position,
                    kpi_key=key,
                    included_in_score=False,
                    weight=weight,
                    evidence_classification="configuration_requires_review",
                    detail=InsightDetail(
                        current_value=actual,
                        previous_value=previous_actual,
                        target_value=None,
                        unit=unit,
                        direction=direction,
                        warnings=["Target is missing or zero; calculated results are unavailable."],
                        recommended_focus="Correct the effective KPI target before using this KPI in performance interpretation.",
                    ),
                )
                analyses.append(configuration_item)
                items.append(configuration_item)
                continue
            if contribution is None or weight is None:
                continue
            contribution_scale = 100 if max(
                abs(contribution or 0),
                abs(previous_contribution or 0),
            ) <= 1 else 1
            contribution_points = contribution * contribution_scale
            previous_contribution_points = previous_contribution * contribution_scale if previous_contribution is not None else None
            gap_points = max((weight * 100) - contribution_points, 0)
            impact = (
                contribution_points - previous_contribution_points
                if previous_contribution_points is not None
                else -gap_points
            )
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

            achievement = _target_achievement(actual, target, direction)
            is_positive = impact > 0 or (exceeds_target and impact >= 0)
            # A high KPI weight increases priority, but a near-target result is not
            # automatically a critical failure. Critical is reserved for results
            # below 80% target achievement (or an unmeasurable severe score loss).
            severity = (
                "opportunity"
                if not target_missed
                else "critical"
                if (achievement is not None and achievement < .8)
                or (achievement is None and impact <= -10)
                else "risk"
            )
            if target_missed and weight >= .15:
                high_weight_misses.add((team, key))

            narrative, movement_positive, target_missed, exceeds_target = _analysis_narrative(
                label, actual, previous_actual, target, unit, direction
            )
            impact_text = (
                f"Its weighted contribution moved the overall score by {impact:+.1f}% versus the comparison period."
                if previous_contribution is not None
                else f"It accounts for approximately {gap_points:.1f}% of the current overall score gap."
            )
            relation = "above" if direction == "lower_better" else "below"
            if movement_positive and target_missed:
                title = f"{label} is improving but remains {relation} target"
                trend_label = f"Improving · Still {relation} target"
            elif target_missed:
                title = f"{label} contributed to the performance gap"
                trend_label = "Compared with previous available period" if previous_values else "Current-period gap"
            else:
                title = f"{label} is a positive score driver" if is_positive else f"{label} is on target"
                trend_label = "Target achieved"
            item = self._make_item(
                severity=severity,
                insight_type="opportunity" if is_positive else "kpi_driver",
                title=title,
                explanation=f"{narrative} {impact_text}",
                scope_label=f"{team} · {position}",
                trend_label=trend_label,
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
                        InsightEvidence(
                            label="Target achievement",
                            value=f"{achievement * 100:.1f}%" if achievement is not None else "Not available",
                        ),
                        InsightEvidence(label="Applied KPI weight", value=f"{weight * 100:.1f}%"),
                        InsightEvidence(label="Measured KPI rows", value=str(len(values))),
                    ],
                    warnings=["Zero targets are not converted into achievement percentages."] if target == 0 else [],
                    recommended_focus=_kpi_recommended_focus(label, direction, target_missed=target_missed),
                ),
            )
            analyses.append(item)
            relevant = abs(impact) >= 1 or (weight >= .15 and target_missed) or exceeds_target
            if not relevant:
                continue
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
        return items, analyses, drivers, high_weight_misses

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
            1 for record in current for kpi in _configured_kpi_values(record)
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
            1 for record in current for kpi in _configured_kpi_values(record)
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
            for kpi in _configured_kpi_values(record):
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
        options = self._options(authorized_records, filters)
        records = self._filter_records(authorized_records, filters)
        explicit_periods = sorted({_period(record) for record in records if _period(record)})
        today = date.today()
        completed_periods = [period for period in explicit_periods if period < (today.year, today.month)]

        requested_period = None
        if filters.get("year") and filters.get("month"):
            month_number = MONTH_ORDER.get(str(filters["month"]))
            if not month_number:
                raise InsightValidationError("Unknown insight month")
            requested_period = (int(filters["year"]), month_number)
        current_period = requested_period or (completed_periods[-1] if completed_periods else (explicit_periods[-1] if explicit_periods else None))
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

        adjacent_period = (current_period[0] - 1, 12) if current_period[1] == 1 else (current_period[0], current_period[1] - 1)
        previous_period = adjacent_period if adjacent_period in explicit_periods else None
        current = [record for record in records if _period(record) == current_period]
        previous = [record for record in records if previous_period and _period(record) == previous_period]

        items = self._score_insights(current, previous, current_period, previous_period)
        kpi_items, team_analyses, drivers, high_weight_misses = self._kpi_insights(current, previous)
        operational_analyses = self._operational_kpi_insights(current, previous)
        team_analyses.extend(operational_analyses)
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
        items.extend(operational_analyses)
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
        filtered_team_analyses = [
            item for item in team_analyses
            if (not selected_kpi or item.kpi_key == selected_kpi)
            and (not selected_severity or item.severity == selected_severity)
            and (not selected_type or item.insight_type == selected_type)
            and (not selected_status or item.status == selected_status)
        ]
        priority_items = sorted_items[:50]
        item_ids = {item.id for item in sorted_items}
        scoped_drivers = sorted(
            [driver for driver in drivers if driver.insight_id in item_ids],
            key=lambda driver: (-abs(driver.impact_points), driver.id),
        )
        visible_drivers = scoped_drivers[:10]
        opportunities = [item for item in sorted_items if item.severity == "opportunity"]
        visible_data_issues = [item for item in sorted_items if item.insight_type == "data_quality"]

        selected_kpi_key = str(selected_kpi or "")
        expected_kpis = 0
        analyzed_kpis = 0
        for record in current:
            for kpi in _configured_kpi_values(record):
                key = str(_value(kpi, "kpi_key", ""))
                if selected_kpi_key and key != selected_kpi_key:
                    continue
                expected_kpis += 1
                target = _value(kpi, "target_value")
                if (
                    key
                    and _value(kpi, "actual_value") is not None
                    and target is not None
                    and float(target) > 0
                    and _value(kpi, "contribution") is not None
                    and _value(kpi, "weight_applied") is not None
                    and _value(kpi, "direction") in {"higher_better", "lower_better"}
                ):
                    analyzed_kpis += 1

        critical_issue_keys = {
            (item.team or "", item.position or "All positions", item.kpi_key or item.title)
            for item in filtered_team_analyses
            if item.severity == "critical"
        }
        weighted_analyses = [item for item in filtered_team_analyses if item.impact_points is not None]
        negative_impact = sum(abs(item.impact_points or 0) for item in weighted_analyses if (item.impact_points or 0) < 0)
        positive_impact = sum(item.impact_points or 0 for item in weighted_analyses if (item.impact_points or 0) > 0)
        summary = InsightSummary(
            critical=sum(item.severity == "critical" for item in sorted_items),
            at_risk=sum(item.severity == "risk" for item in sorted_items),
            opportunities=len(opportunities),
            data_issues=len(visible_data_issues),
            critical_issues=len(critical_issue_keys),
            negative_weighted_drivers=sum((item.impact_points or 0) < 0 for item in weighted_analyses),
            positive_weighted_drivers=sum((item.impact_points or 0) > 0 for item in weighted_analyses),
            weighted_negative_impact=round(negative_impact, 2),
            weighted_positive_impact=round(positive_impact, 2),
            weighted_net_impact=round(positive_impact - negative_impact, 2),
            analyzed_kpis=analyzed_kpis,
            expected_kpis=expected_kpis,
            coverage_percent=round((analyzed_kpis / expected_kpis) * 100, 1) if expected_kpis else None,
        )

        analyses_by_team: dict[str, list[InsightItem]] = defaultdict(list)
        for item in filtered_team_analyses:
            if item.team:
                analyses_by_team[item.team].append(item)
        current_by_team: dict[str, list[Any]] = defaultdict(list)
        previous_by_team: dict[str, list[Any]] = defaultdict(list)
        for record in current:
            current_by_team[str(_value(record, "team", ""))].append(record)
        for record in previous:
            previous_by_team[str(_value(record, "team", ""))].append(record)

        team_summaries: list[InsightTeamSummary] = []
        for team in sorted(current_by_team):
            team_records = current_by_team[team]
            previous_records = previous_by_team.get(team, [])
            current_score = _average(_evaluation_value(record, "score") for record in team_records)
            previous_score = _average(_evaluation_value(record, "score") for record in previous_records)
            team_items = analyses_by_team.get(team, [])
            ranked_items = self._sort_items(team_items)
            employee_ids = {
                str(_value(record, "employee_id"))
                for record in team_records
                if _value(record, "employee_id")
            }
            impacted_ids = {
                str(_value(record, "employee_id"))
                for record in team_records
                if _value(record, "employee_id")
                and _evaluation_value(record, "score") is not None
                and float(_evaluation_value(record, "score")) < 70
            }
            team_summaries.append(InsightTeamSummary(
                team=team,
                current_score=round(current_score, 1) if current_score is not None else None,
                previous_score=round(previous_score, 1) if previous_score is not None else None,
                score_change=round(current_score - previous_score, 1) if current_score is not None and previous_score is not None else None,
                impacted_employees=len(impacted_ids),
                total_employees=len(employee_ids) or len(team_records),
                critical=len({(item.position or "", item.kpi_key or item.title) for item in team_items if item.severity == "critical"}),
                at_risk=len({(item.position or "", item.kpi_key or item.title) for item in team_items if item.severity == "risk"}),
                opportunities=len({(item.position or "", item.kpi_key or item.title) for item in team_items if item.severity == "opportunity"}),
                main_insight_id=ranked_items[0].id if ranked_items else None,
                main_cause=ranked_items[0].title if ranked_items else None,
            ))
        team_summaries.sort(key=lambda item: (-item.critical, -item.at_risk, item.current_score if item.current_score is not None else 101, item.team))

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
            team_analyses=self._sort_items(filtered_team_analyses)[:100],
            performance_drivers=visible_drivers,
            risks=risk_cards,
            opportunities=opportunities,
            data_issues=visible_data_issues,
            team_summaries=team_summaries,
            options=options,
            comparison=InsightComparison(current=current_schema, previous=previous_schema, is_adjacent=adjacent, note=comparison_note),
            deferred_capabilities=["Overdue corrective actions require a persisted due date, which is not available in the current action model."],
        )
