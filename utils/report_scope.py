from __future__ import annotations


def _record_value(record, field: str, default=""):
    if isinstance(record, dict):
        return record.get(field, default)
    return getattr(record, field, default)


def user_can_access_team(scope: dict, team_name: str) -> bool:
    if scope.get("legacy_unscoped"):
        return True
    if scope.get("role") == "Admin" or scope.get("is_general_manager"):
        return True
    accessible = {str(team).lower() for team in scope.get("accessible_teams", [])}
    return team_name.lower() in accessible


def user_can_access_team_level(scope: dict, team_name: str, performance_level: str) -> bool:
    if scope.get("legacy_unscoped"):
        return False
    if scope.get("role") == "Admin" or scope.get("is_general_manager"):
        return True
    if not user_can_access_team(scope, team_name):
        return False
    configured = {
        (str(team).lower(), str(level))
        for team, level in scope.get("accessible_team_levels", [])
    }
    team_levels = {level for team, level in configured if team == team_name.lower()}
    return not team_levels or performance_level in team_levels


def filter_records_by_scope(records, scope: dict):
    if scope.get("legacy_unscoped"):
        return records
    role = scope.get("role")
    if role in {"Agent", "Executive"}:
        self_id = str(scope.get("employee_id") or scope.get("user_id") or "")
        return [record for record in records if str(_record_value(record, "employee_id")) == self_id]
    if role == "Manager" and not scope.get("is_general_manager"):
        accessible = {str(team).lower() for team in scope.get("accessible_teams", [])}
        return [record for record in records if str(_record_value(record, "team")).lower() in accessible]
    return records


def filter_records_by_team_levels(records, scope: dict):
    """Apply explicit team/level assignments after the broader role scope filter."""
    if scope.get("role") == "Admin" or scope.get("is_general_manager") or scope.get("legacy_unscoped"):
        return records
    configured = {
        (str(team).lower(), str(level))
        for team, level in scope.get("accessible_team_levels", [])
    }
    if not configured:
        return records
    return [
        record
        for record in records
        if (
            str(_record_value(record, "team")).lower(),
            str(_record_value(record, "performance_level")),
        ) in configured
    ]
