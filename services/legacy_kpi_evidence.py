from __future__ import annotations

import math
from typing import Any, Mapping


LEGACY_EMPLOYEE_TEAMS = {
    "Inbound",
    "Outbound",
    "Inbound UAE",
    "Pre-Approvals IP Offshore",
}


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _weight(weights: Mapping[str, float], key: str) -> float:
    normalized_weights = {str(name).casefold(): value for name, value in weights.items()}
    aliases = {
        "Attendance": ("Attendance", "Attend"),
        "Booking": ("Booking",),
        "Quality": ("Quality",),
        "AHT": ("AHT",),
        "Other": ("Other",),
        "Rejection": ("Rejection",),
        "InitialError": ("InitialError",),
        "Submission": ("Submission",),
    }
    for alias in aliases.get(key, (key,)):
        value = _number(normalized_weights.get(alias.casefold()))
        if value is not None:
            return max(value, 0.0)
    return 0.0


def _target(actual: float, achievement: float, direction: str, fallback: float) -> float:
    if achievement > 0:
        if direction == "lower_better":
            if actual > 0:
                return round(actual * achievement, 6)
        else:
            return round(actual / achievement, 6)
    return fallback


def build_legacy_employee_kpi_values(
    team: str,
    row: Mapping[str, Any],
    *,
    achievements: Mapping[str, float] | None = None,
    weights: Mapping[str, float] | None = None,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the canonical KPI evidence for legacy formula-based teams.

    These teams calculate their score from normalized source fields rather
    than directly from the static config columns. Persisting the static
    columns previously stored Excel time fractions and zero/mismatched
    targets. This builder is shared by ingestion and the compatibility read
    path so existing rows and future uploads expose the same evidence.
    """

    if team not in LEGACY_EMPLOYEE_TEAMS:
        return []

    evidence_keys = {
        "Inbound": ("A.Attend%", "A.Booking%", "A.QualityScore", "AHT_Minutes", "A.UTZ%", "A.AbandonRate%"),
        "Outbound": ("A.Attend%", "A.Booking%", "A.QualityScore", "A.Reachability%"),
        "Inbound UAE": ("A.Attend%", "A.Booking%", "A.AbandonRate%"),
        "Pre-Approvals IP Offshore": ("IPInitialRejection%", "Error%", "NumberApprovalwithin48hrs"),
    }
    if not any(_first(row, key) is not None for key in evidence_keys[team]):
        return []

    achievements = achievements or {}
    weights = weights or {}
    definitions = {
        str(item.get("key")): item
        for item in (config or {}).get("kpis", [])
        if item.get("key")
    }

    if team == "Inbound":
        has_utz = _first(row, "A.UTZ%", "UTZ%") is not None
        specs = [
            ("Attendance", "Attendance Rate", "higher_better", _first(row, "A.Attend%"), _first(row, "Attend%Ach%"), 0.75),
            ("Booking", "Booking Rate", "higher_better", _first(row, "A.Booking%"), _first(row, "Booking%Ach%"), 0.45),
            ("Quality", "Quality Score", "higher_better", _first(row, "A.QualityScore"), _first(row, "QualityTargetAch%"), 0.95),
            ("AHT", "AHT (Handle Time)", "lower_better", _first(row, "AHT_Minutes"), _first(row, "AHTAch%"), 2.5),
            (
                "Other",
                "Utilization" if has_utz else "Abandon Rate",
                "higher_better" if has_utz else "lower_better",
                _first(row, "A.UTZ%", "UTZ%") if has_utz else _first(row, "A.AbandonRate%"),
                _first(row, "UTZ%Ach%") if has_utz else _first(row, "AbandonRate%Ach%"),
                0.85 if has_utz else 0.01,
            ),
        ]
    elif team == "Outbound":
        specs = [
            ("Attendance", "Attendance Rate", "higher_better", _first(row, "A.Attend%"), _first(row, "AttendC.RAch%", "Attend%Ach%"), 0.55),
            ("Booking", "Booking Rate", "higher_better", _first(row, "A.Booking%"), _first(row, "BookingC.RAch%", "Booking%Ach%"), 0.46),
            ("Quality", "Quality Score", "higher_better", _first(row, "A.QualityScore"), _first(row, "QualityAch%", "QualityTargetAch%"), 0.95),
            ("Other", "Reachability", "higher_better", _first(row, "A.Reachability%"), _first(row, "Reachability%Ach%"), 0.75),
        ]
    elif team == "Inbound UAE":
        specs = [
            ("Attendance", "Attendance Rate", "higher_better", _first(row, "A.Attend%"), _first(row, "AttendC.RAch%", "Attend%Ach%"), 0.75),
            ("Booking", "Booking Rate", "higher_better", _first(row, "A.Booking%"), _first(row, "BookingC.RAch%", "Booking%Ach%"), 0.60),
            ("Other", "Abandon Rate", "lower_better", _first(row, "A.AbandonRate%"), _first(row, "AbandonRateAch%", "AbandonRate%Ach%"), 0.01),
        ]
    else:
        specs = [
            ("Rejection", "Rejection Rate", "lower_better", _first(row, "IPInitialRejection%"), _first(row, "RejectionRate"), 0.03),
            ("InitialError", "Initial Error Rate", "lower_better", _first(row, "Error%"), _first(row, "InitialError%"), 0.03),
            ("Submission", "Submission Rate", "higher_better", _first(row, "NumberApprovalwithin48hrs"), _first(row, "%ofSubmissionWithinDuedate"), 0.90),
        ]

    result: list[dict[str, Any]] = []
    achievement_alias = {
        "Attendance": "Attend",
        "Booking": "Booking",
        "Quality": "Quality",
        "AHT": "AHT",
        "Other": "Other",
        "Rejection": "Rejection",
        "InitialError": "InitialError",
        "Submission": "Submission",
    }
    for key, label, direction, actual_value, row_achievement, fallback_target in specs:
        actual = max(actual_value or 0.0, 0.0)
        supplied_achievement = _number(achievements.get(achievement_alias[key]))
        achievement = max(supplied_achievement if supplied_achievement is not None else (row_achievement or 0.0), 0.0)
        weight = _weight(weights, key)
        definition = definitions.get(key, {})
        target = _target(actual, achievement, direction, fallback_target)
        result.append({
            "kpi_key": key,
            "label": label,
            "perspective": definition.get("perspective"),
            "unit": definition.get("unit", "%" if key != "AHT" else "min"),
            "color": definition.get("color", "#3B82F6"),
            "direction": direction,
            "actual_value": actual,
            "target_value": target,
            "achievement_ratio": achievement,
            "weight_applied": weight,
            "contribution": min(achievement, 1.0) * weight,
        })
    return result
