from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any, Iterable


MONTHS = {
    name: index
    for index, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
        start=1,
    )
}


def _value(item: Any, key: str, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def _record_year(record: Any) -> int | None:
    year = _value(record, "year")
    if year:
        return int(year)
    raw = _value(record, "raw_data", {}) or {}
    date = raw.get("Date") or raw.get("date")
    try:
        return datetime.fromisoformat(str(date).replace("Z", "+00:00")).year
    except (TypeError, ValueError):
        return None


def _period_key(record: Any) -> tuple[int, int]:
    return (_record_year(record) or 0, MONTHS.get(str(_value(record, "month", "")), 0))


def _rollup(values: list[float], mode: str) -> float | None:
    if not values:
        return None
    if mode == "sum":
        return sum(values)
    if mode == "latest":
        return values[-1]
    return mean(values)


def _status(score: float | None, thresholds: dict[str, float], state: str) -> str:
    if state == "not_configured":
        return "Not Configured"
    if score is None:
        return "No Data"
    if score >= float(thresholds.get("A", 90)):
        return "Excellent"
    if score >= float(thresholds.get("C", 70)):
        return "Good"
    return "Needs Attention"


class BalancedScorecardService:
    """Builds one BSC response from already-authorized performance records."""

    @staticmethod
    def _kpi_values(records: Iterable[Any], key: str) -> list[Any]:
        return [
            value
            for record in records
            for value in (_value(record, "kpi_values", []) or [])
            if _value(value, "kpi_key") == key
        ]

    @classmethod
    def _summarize(cls, records: list[Any], config: dict[str, Any]) -> dict[str, Any]:
        thresholds = config.get("grade_thresholds", {})
        bsc = config["balanced_scorecard"]
        definitions = config.get("kpis", [])
        kpi_rows = []

        for definition in definitions:
            values = cls._kpi_values(records, definition["key"])
            configured_weight = float(definition.get("weight", 0))
            mode = definition.get("rollup", "average")
            contributions = [float(_value(value, "contribution")) for value in values if _value(value, "contribution") is not None]
            achievements = [float(_value(value, "achievement_ratio")) for value in values if _value(value, "achievement_ratio") is not None]
            actuals = [float(_value(value, "actual_value")) for value in values if _value(value, "actual_value") is not None]
            targets = [float(_value(value, "target_value")) for value in values if _value(value, "target_value") is not None]
            applied_weights = [float(_value(value, "weight_applied")) for value in values if _value(value, "weight_applied") is not None]
            weight = mean(applied_weights) if applied_weights else configured_weight
            contribution = mean(contributions) if contributions else None
            score = contribution / weight * 100 if contribution is not None and weight else None
            state = "measured" if contribution is not None else "no_data"
            kpi_rows.append({
                "kpi_key": definition["key"],
                "kpi_label": definition.get("label", definition["key"]),
                "perspective": definition["perspective"],
                "direction": definition.get("direction", "higher_better"),
                "unit": definition.get("unit", "%"),
                "color": definition.get("color"),
                "rollup": mode,
                "weight": weight,
                "actual_value": _rollup(actuals, mode),
                "target_value": _rollup(targets, mode),
                "raw_achievement_ratio": mean(achievements) if achievements else None,
                "score": score,
                "weighted_contribution": contribution,
                "performance_gap": max(weight - contribution, 0) if contribution is not None else None,
                "record_count": len(values),
                "state": state,
                "status": _status(score, thresholds, state),
            })

        perspectives = []
        for metadata in sorted(bsc["perspectives"], key=lambda item: item.get("display_order", 0)):
            rows = [row for row in kpi_rows if row["perspective"] == metadata["key"]]
            configured_weight = sum(row["weight"] for row in rows)
            measured = [row for row in rows if row["weighted_contribution"] is not None]
            measured_weight = sum(row["weight"] for row in measured)
            contribution = sum(row["weighted_contribution"] for row in measured)
            score = contribution / measured_weight * 100 if measured_weight else None
            state = "not_configured" if not rows else "measured" if len(measured) == len(rows) else "partial_data" if measured else "no_data"
            driver = max(measured, key=lambda row: row["weighted_contribution"], default=None)
            risk = max(measured, key=lambda row: row["performance_gap"], default=None)
            perspectives.append({
                **metadata,
                "target_score": 100.0,
                "configured_weight": configured_weight,
                "measured_weight": measured_weight,
                "coverage": measured_weight / configured_weight if configured_weight else None,
                "weighted_contribution": contribution if measured else None,
                "score": score,
                "state": state,
                "status": _status(score, thresholds, state),
                "kpi_count": len(rows),
                "record_count": sum(row["record_count"] for row in rows),
                "primary_driver": driver,
                "primary_risk": risk,
                "kpis": rows,
            })

        configured_weight = sum(row["weight"] for row in kpi_rows)
        measured = [row for row in kpi_rows if row["weighted_contribution"] is not None]
        measured_weight = sum(row["weight"] for row in measured)
        contribution = sum(row["weighted_contribution"] for row in measured)
        score = contribution / measured_weight * 100 if measured_weight else None
        state = "measured" if measured and len(measured) == len(kpi_rows) else "partial_data" if measured else "no_data"
        return {
            "scorecard": {
                "score": score,
                "target_score": 100.0,
                "status": _status(score, thresholds, state),
                "state": state,
                "configured_weight": configured_weight,
                "measured_weight": measured_weight,
                "coverage": measured_weight / configured_weight if configured_weight else None,
                "weighted_contribution": contribution if measured else None,
                "record_count": len(records),
                "kpi_count": len(kpi_rows),
            },
            "perspectives": perspectives,
            "kpi_table": kpi_rows,
        }

    @classmethod
    def _contributors(cls, records: list[Any], perspectives: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for record in records:
            person = {
                "employee_id": str(_value(record, "employee_id", "")),
                "employee_name": _value(record, "employee_name", ""),
                "perspectives": {},
            }
            for perspective in perspectives:
                keys = {kpi["kpi_key"] for kpi in perspective["kpis"]}
                values = [value for value in (_value(record, "kpi_values", []) or []) if _value(value, "kpi_key") in keys]
                measured = [value for value in values if _value(value, "contribution") is not None]
                contribution = sum(float(_value(value, "contribution")) for value in measured)
                weight = sum(float(_value(value, "weight_applied", 0) or 0) for value in measured)
                top_value = max(measured, key=lambda value: float(_value(value, "contribution") or 0), default=None)
                top_key = _value(top_value, "kpi_key") if top_value else None
                top_kpi = next((kpi for kpi in perspective["kpis"] if kpi["kpi_key"] == top_key), None)
                person["perspectives"][perspective["key"]] = {
                    "score": contribution / weight * 100 if weight else None,
                    "weighted_contribution": contribution if measured else None,
                    "measured_weight": weight if measured else None,
                    "top_kpi_label": top_kpi["kpi_label"] if top_kpi else None,
                    "trend": None,
                    "kpis": {str(_value(value, "kpi_key")): _value(value, "actual_value") for value in values},
                }
            rows.append(person)
        return rows

    @classmethod
    def build(
        cls,
        records: list[Any],
        config: dict[str, Any],
        team: str,
        performance_level: str,
        month: str | None = None,
        year: int | None = None,
        employee_ids: list[str] | None = None,
        history_months: int = 6,
        selected_kpi: str | None = None,
        period_configs: dict[tuple[int, int], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        periods = sorted({_period_key(record) for record in records if _period_key(record)[0] and _period_key(record)[1]})
        if month and month != "All":
            selected_period = (year or 0, MONTHS.get(month, 0))
        else:
            selected_period = periods[-1] if periods else None

        people_by_id = {}
        for record in records:
            raw_data = _value(record, "raw_data", {}) or {}
            people_by_id[str(_value(record, "employee_id", ""))] = {
                "employee_id": str(_value(record, "employee_id", "")),
                "employee_name": _value(record, "employee_name", ""),
                "team_name": _value(record, "team", team),
                "role": raw_data.get("Position") or raw_data.get("position"),
            }
        selected_ids = set(employee_ids or [])
        scoped_records = [record for record in records if not selected_ids or str(_value(record, "employee_id", "")) in selected_ids]
        current = [record for record in scoped_records if selected_period and _period_key(record) == selected_period]
        current_config = (period_configs or {}).get(selected_period, config)
        summary = cls._summarize(current, current_config)
        history_periods = [period for period in periods if not selected_period or period <= selected_period]
        history_periods = history_periods[-max(1, min(history_months, 24)):]

        history = []
        for period in history_periods:
            period_records = [record for record in scoped_records if _period_key(record) == period]
            period_summary = cls._summarize(period_records, (period_configs or {}).get(period, config))
            history.append({
                "month": next(name for name, number in MONTHS.items() if number == period[1]),
                "year": period[0],
                **period_summary["scorecard"],
                "perspective_scores": {item["key"]: item["score"] for item in period_summary["perspectives"]},
            })

        previous_history = history[-2] if len(history) >= 2 else None
        for perspective in summary["perspectives"]:
            previous_score = (previous_history or {}).get("perspective_scores", {}).get(perspective["key"])
            perspective["trend_vs_previous"] = (
                perspective["score"] - previous_score
                if perspective["score"] is not None and previous_score is not None
                else None
            )

        selected = next((row for row in summary["kpi_table"] if row["kpi_key"] == selected_kpi), None)
        if selected is None:
            selected = max(
                (row for row in summary["kpi_table"] if row["performance_gap"] is not None),
                key=lambda row: row["performance_gap"],
                default=None,
            )
        selected_history = []
        if selected:
            for period in history_periods:
                period_records = [record for record in scoped_records if _period_key(record) == period]
                period_config = (period_configs or {}).get(period, config)
                row = next(
                    (
                        item for item in cls._summarize(period_records, period_config)["kpi_table"]
                        if item["kpi_key"] == selected["kpi_key"]
                    ),
                    None,
                )
                if not row or not row["record_count"] or row["score"] is None:
                    continue
                selected_history.append({
                    "month": next(name for name, number in MONTHS.items() if number == period[1]),
                    "year": period[0],
                    **row,
                })

        contributors = cls._contributors(current, summary["perspectives"])
        if selected_period:
            for contributor in contributors:
                previous_periods = sorted({
                    _period_key(record)
                    for record in scoped_records
                    if str(_value(record, "employee_id", "")) == contributor["employee_id"]
                    and _period_key(record) < selected_period
                })
                if not previous_periods:
                    continue
                previous_period = previous_periods[-1]
                previous_records = [
                    record for record in scoped_records
                    if str(_value(record, "employee_id", "")) == contributor["employee_id"]
                    and _period_key(record) == previous_period
                ]
                previous_config = (period_configs or {}).get(previous_period, config)
                previous_perspectives = cls._summarize(previous_records, previous_config)["perspectives"]
                previous_contributor = cls._contributors(previous_records, previous_perspectives)[0]
                for key, current_perspective in contributor["perspectives"].items():
                    previous_score = previous_contributor["perspectives"][key]["score"]
                    current_score = current_perspective["score"]
                    current_perspective["trend"] = (
                        current_score - previous_score
                        if current_score is not None and previous_score is not None
                        else None
                    )

        return {
            "team": {"name": team, "performance_level": performance_level, "balanced_scorecard": True},
            "selection": {
                "month": next((name for name, number in MONTHS.items() if selected_period and number == selected_period[1]), None),
                "year": selected_period[0] if selected_period else None,
                "employee_ids": sorted(selected_ids),
                "people_count": len({str(_value(record, "employee_id", "")) for record in current}),
                "history_months": history_months,
            },
            "available_periods": [
                {"month": next(name for name, number in MONTHS.items() if number == period[1]), "year": period[0]}
                for period in periods
            ],
            "available_people": sorted(people_by_id.values(), key=lambda person: (person["employee_name"], person["employee_id"])),
            **summary,
            "strategy_map": {"links": config["balanced_scorecard"].get("strategy_map_links", [])},
            "contributors": contributors,
            "history": history,
            "selected_kpi": {
                "key": selected["kpi_key"],
                "label": selected["kpi_label"],
                "current": selected,
                "history": selected_history,
            } if selected else None,
        }
