import pandas as pd
from fastapi import Header, HTTPException, Request
from typing import List, Dict, Any

from repositories.json_repos import (
    JSONPerformanceRepository, JSONEmployeeRepository,
    JSONKPIWeightsRepository, JSONTargetsRepository, JSONUploadsRepository,
    JSONManagerNotesRepository, JSONCorrectiveActionsRepository,
    JSONUserRepository
)
from processors.excel_processor import ExcelProcessor
from services.kpi_service import KPIService
from services.analysis_service import AnalysisService
from services.learning_service import LearningService
from services.planning_service import PlanningService
from services.trend_service import TrendService
from services.insights_service import InsightsService

# Instantiate JSON-based repositories (single source of truth)
performance_repo = JSONPerformanceRepository()
employee_repo = JSONEmployeeRepository()
weights_repo = JSONKPIWeightsRepository()
targets_repo = JSONTargetsRepository()
uploads_repo = JSONUploadsRepository()
notes_repo = JSONManagerNotesRepository()
actions_repo = JSONCorrectiveActionsRepository()
user_repo = JSONUserRepository()

# Instantiate services
kpi_service = KPIService(weights_repo, targets_repo)
analysis_service = AnalysisService(targets_repo)
learning_service = LearningService(actions_repo)
planning_service = PlanningService(performance_repo)
trend_service = TrendService()
insights_service = InsightsService(performance_repo, planning_service)
excel_processor = ExcelProcessor()

def safe_float(val) -> float:
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def get_overall_trend_label(trend_status) -> str:
    if isinstance(trend_status, dict):
        return trend_status.get("score", {}).get("mom", "Stable")
    return trend_status or "Stable"

def serialize_performance_record(r) -> Dict[str, Any]:
    # Reconstruct GeoBreakdown totals
    geo_bookings = {
        "dubai": r.geo.bookings.dubai,
        "sharjah": r.geo.bookings.sharjah,
        "ajman": r.geo.bookings.ajman,
        "clinics": r.geo.bookings.clinics
    }
    geo_attended = {
        "dubai": r.geo.attended.dubai,
        "sharjah": r.geo.attended.sharjah,
        "ajman": r.geo.attended.ajman,
        "clinics": r.geo.attended.clinics
    }
    
    # Resolve actual values with fallback to raw_data if database field is missing/zero
    actual_booking = r.actual.booking_rate or safe_float(r.raw_data.get("A.Booking%", 0.0))
    actual_attend = r.actual.attend_rate or safe_float(r.raw_data.get("A.Attend%", 0.0))
    actual_abandon = r.actual.abandon_rate or safe_float(r.raw_data.get("A.AbandonRate%", 0.0))
    actual_reachability = r.actual.reachability_rate or safe_float(r.raw_data.get("A.Reachability%", 0.0))
    actual_rejection = r.actual.rejection_rate or safe_float(r.raw_data.get("IPInitialRejection%", 0.0))
    actual_error = r.actual.initial_error_rate or safe_float(r.raw_data.get("Error%", 0.0))
    actual_submission = r.actual.submission_rate or safe_float(r.raw_data.get("NumberApprovalwithin48hrs", 0.0))
    actual_quality = getattr(r.actual, "quality_rate", 0.0) or safe_float(r.raw_data.get("A.QualityScore", 0.0))
    actual_utz = getattr(r.actual, "utz_rate", 0.0) or safe_float(r.raw_data.get("A.UTZ%", 0.0))

    aht_raw = r.calls.aht_raw
    if aht_raw == "00:00:00" or not aht_raw:
        aht_mins = r.raw_data.get("AHT_Minutes") or safe_float(r.raw_data.get("A.AHT", 0.0)) or safe_float(r.raw_data.get("AHT", 0.0))
        if aht_mins > 0:
            if aht_mins < 1.0 and not r.raw_data.get("AHT_Minutes"):
                aht_mins = aht_mins * 24.0 * 60.0
            from utils.helpers import format_minutes_to_hhmmss
            aht_raw = format_minutes_to_hhmmss(aht_mins)

    return {
        "id": r.id,
        "employee_id": r.employee_id,
        "employee_name": r.employee_name,
        "team": r.team,
        "month": r.month,
        "region": getattr(r, "region", "EGY") or "EGY",
        "identity": {
            "name": r.employee_name,
            "month": r.month,
            "team": r.team,
            "employee_id": r.employee_id
        },
        "calls": {
            "inbound": r.calls.inbound,
            "outbound": r.calls.outbound,
            "total_handled": r.calls.total_handled,
            "abandoned": r.calls.abandoned,
            "aht_raw": aht_raw
        },
        "geo": {
            "bookings": geo_bookings,
            "attended": geo_attended
        },
        "actual": {
            "booking_rate": actual_booking,
            "attend_rate": actual_attend,
            "abandon_rate": actual_abandon,
            "reachability_rate": actual_reachability,
            "rejection_rate": actual_rejection,
            "initial_error_rate": actual_error,
            "submission_rate": actual_submission,
            "quality_rate": actual_quality,
            "utz_rate": actual_utz
        },
        "achievement": {
            "booking_ach": r.achievement.booking_ach,
            "attend_ach": r.achievement.attend_ach,
            "quality_ach": r.achievement.quality_ach,
            "aht_ach": r.achievement.aht_ach,
            "reachability_ach": r.achievement.reachability_ach,
            "abandon_ach": r.achievement.abandon_ach,
            "rejection_ach": r.achievement.rejection_ach,
            "initial_error_ach": r.achievement.initial_error_ach,
            "submission_ach": r.achievement.submission_ach,
            "op_census_ach": getattr(r.achievement, "op_census_ach", 0.0),
            "op_revenue_ach": getattr(r.achievement, "op_revenue_ach", 0.0),
            "ip_census_ach": getattr(r.achievement, "ip_census_ach", 0.0),
            "ip_revenue_ach": getattr(r.achievement, "ip_revenue_ach", 0.0),
            "activity_ach": getattr(r.achievement, "activity_ach", 0.0)
        },
        "evaluation": {
            "score": r.evaluation.score,
            "grade": r.evaluation.grade,
            "root_cause": r.evaluation.root_cause.model_dump() if r.evaluation.root_cause else None,
            "suggested_action": r.evaluation.suggested_action,
            "corrective_action": r.evaluation.corrective_action,
            "manager_notes": r.evaluation.manager_notes,
            "planning_category": r.evaluation.planning_category,
            "trend_status": get_overall_trend_label(r.evaluation.trend_status)
        },
        "raw_data": r.raw_data
    }

def require_role(allowed_roles: List[str]):
    def dependency(
        request: Request,
        x_user_role: str = Header(default="Viewer", alias="X-User-Role")
    ):
        # Check if JWT session is attached to request state
        role = x_user_role
        if hasattr(request.state, "user") and request.state.user:
            role = request.state.user.get("role", x_user_role)

        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied for role '{role}'. Required: {allowed_roles}"
            )
        return role
    return dependency
