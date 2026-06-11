import sys
from pathlib import Path

# Compute project root (parent of the api/ directory) and insert into sys.path if not present
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Header
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
import datetime
import math
import uuid
import pandas as pd
import numpy as np
import io

from models.schemas import (
    StandardResponse, Employee, PerformanceRecord, KPIWeight, Target, UploadRecord, ManagerNote, CorrectiveAction,
    CallsData, GeoBreakdown, GeoData, ActualMetrics, AchievementMetrics, EvaluationData, TeamAction, UserRecord, LoginPayload
)
from repositories.json_repos import (
    JSONEmployeeRepository, JSONPerformanceRepository, JSONKPIWeightsRepository, JSONTargetsRepository,
    JSONUploadsRepository, JSONManagerNotesRepository, JSONCorrectiveActionsRepository, JSONTeamActionsRepository,
    JSONUserRepository
)
from processors.excel_processor import ExcelProcessor
from services.kpi_service import KPIService
from services.analysis_service import AnalysisService
from services.learning_service import LearningService
from services.planning_service import PlanningService
from services.trend_service import TrendService
from services.insights_service import InsightsService
from exports.report_exporter import ReportExporter

def safe_int(val) -> int:
    if pd.isna(val):
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0

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
            "submission_ach": r.achievement.submission_ach
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
        }
    }

router = APIRouter()

# Instantiate repositories
employee_repo = JSONEmployeeRepository()
performance_repo = JSONPerformanceRepository()
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

# Helper for Role Authorization based on X-User-Role header
def require_role(allowed_roles: List[str]):
    def dependency(x_user_role: str = Header(default="Viewer", alias="X-User-Role")):
        if x_user_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied for role '{x_user_role}'. Required: {allowed_roles}"
            )
        return x_user_role
    return dependency

@router.get("/performance", response_model=StandardResponse)
async def get_performance(
    month: str = Query("All"),
    team: str = Query("All")
):
    try:
        records = performance_repo.get_all()
        
        # Apply filters
        if month != "All":
            records = [r for r in records if r.month == month]
        if team != "All":
            records = [r for r in records if r.team == team]

        agent_records = [serialize_performance_record(r) for r in records]

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(agent_records)} performance records successfully.",
            data=agent_records
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to fetch performance data: {str(e)}")


@router.get("/employee/{employee_id}", response_model=StandardResponse)
async def get_employee_profile(employee_id: str):
    try:
        emp = employee_repo.get_by_id(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        records = performance_repo.get_all()
        emp_records = [r for r in records if r.employee_id == employee_id]
        
        # Sort chronologically
        from services.planning_service import MONTH_ORDER
        emp_records.sort(key=lambda x: MONTH_ORDER.get(x.month, 0))

        # Fetch action history
        history = actions_repo.get_history(employee_id)
        history.sort(key=lambda x: x.timestamp, reverse=True)

        profile_data = {
            "employee": emp.model_dump(),
            "performance_history": [serialize_performance_record(r) for r in emp_records],
            "corrective_action_history": [h.model_dump() for h in history]
        }

        return StandardResponse(
            success=True,
            message="Employee profile retrieved successfully",
            data=profile_data
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to retrieve employee profile: {str(e)}")


@router.post("/employee/{employee_id}/notes", response_model=StandardResponse)
async def save_notes(
    employee_id: str,
    payload: Dict[str, str],
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        month = payload.get("month", "")
        notes_text = payload.get("notes", "")

        if not month:
            raise HTTPException(status_code=400, detail="Month is required")

        # Save note record
        note = ManagerNote(
            employee_id=employee_id,
            month=month,
            notes=notes_text,
            updated_at=datetime.datetime.now().isoformat()
        )
        notes_repo.save(note)

        # Update note inside active performance record
        perf = performance_repo.get_by_employee_and_month(employee_id, month)
        if perf:
            perf.evaluation.manager_notes = notes_text
            performance_repo.save(perf)

        return StandardResponse(
            success=True,
            message="Manager notes saved successfully",
            data=note.model_dump()
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to save manager notes: {str(e)}")


@router.post("/employee/{employee_id}/corrective-actions", response_model=StandardResponse)
async def save_corrective_action(
    employee_id: str,
    payload: Dict[str, str],
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        month = payload.get("month", "")
        manager_action = payload.get("manager_action", "")
        manager_notes = payload.get("manager_notes", "")
        action_id = payload.get("id")

        if not month or not manager_action:
            raise HTTPException(status_code=400, detail="Month and Corrective Action are required")

        # Fetch active performance record
        perf = performance_repo.get_by_employee_and_month(employee_id, month)
        if not perf:
            raise HTTPException(status_code=404, detail="Performance record not found for the selected month")

        # Check if we are updating an existing action
        existing_action = None
        if action_id:
            history = actions_repo.get_history(employee_id)
            for a in history:
                if a.id == action_id:
                    existing_action = a
                    break

        if existing_action:
            # Update fields
            existing_action.manager_action = manager_action
            existing_action.manager_notes = manager_notes
            existing_action.timestamp = datetime.datetime.now().isoformat()
            actions_repo.save(existing_action)
            action = existing_action
        else:
            # Create new action
            if not action_id:
                action_id = f"{employee_id}_{month}_{datetime.datetime.now().isoformat()}"

            action = CorrectiveAction(
                id=action_id,
                employee_id=employee_id,
                employee_name=perf.employee_name,
                team=perf.team,
                month=month,
                score=perf.evaluation.score,
                grade=perf.evaluation.grade,
                root_cause=perf.evaluation.root_cause.kpi if perf.evaluation.root_cause else "None",
                suggested_action=perf.evaluation.suggested_action or "None",
                manager_action=manager_action,
                manager_notes=manager_notes,
                timestamp=datetime.datetime.now().isoformat()
            )
            actions_repo.save(action)

        # Update Performance Record latest state with latest action for this month
        remaining = actions_repo.get_history(employee_id)
        latest_for_month = None
        for r in sorted(remaining, key=lambda x: x.timestamp):
            if r.month == month:
                latest_for_month = r

        perf.evaluation.corrective_action = latest_for_month.manager_action if latest_for_month else None
        perf.evaluation.manager_notes = latest_for_month.manager_notes if latest_for_month else None
        performance_repo.save(perf)

        return StandardResponse(
            success=True,
            message="Corrective Action saved successfully",
            data=action.model_dump()
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to save corrective action: {str(e)}")


@router.delete("/employee/{employee_id}/corrective-actions/{action_id}", response_model=StandardResponse)
async def delete_corrective_action(
    employee_id: str,
    action_id: str,
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        # Find the action before deleting it to know the month
        history = actions_repo.get_history(employee_id)
        target_action = None
        for a in history:
            if a.id == action_id:
                target_action = a
                break

        if not target_action:
            raise HTTPException(status_code=404, detail="Corrective Action not found")

        month = target_action.month
        actions_repo.delete(action_id)

        # Get the new latest action for this month
        remaining = actions_repo.get_history(employee_id)
        latest_for_month = None
        for r in sorted(remaining, key=lambda x: x.timestamp):
            if r.month == month:
                latest_for_month = r

        perf = performance_repo.get_by_employee_and_month(employee_id, month)
        if perf:
            perf.evaluation.corrective_action = latest_for_month.manager_action if latest_for_month else None
            perf.evaluation.manager_notes = latest_for_month.manager_notes if latest_for_month else None
            performance_repo.save(perf)

        return StandardResponse(
            success=True,
            message="Corrective Action deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to delete corrective action: {str(e)}")


@router.get("/employee/{employee_id}/recommendations", response_model=StandardResponse)
async def get_action_recommendations(employee_id: str, month: str = Query(...)):
    try:
        perf = performance_repo.get_by_employee_and_month(employee_id, month)
        if not perf:
            raise HTTPException(status_code=404, detail="Performance record not found")

        root_kpi = perf.evaluation.root_cause.kpi if perf.evaluation.root_cause else "None"
        default_suggest = perf.evaluation.suggested_action or "Performance Monitoring"

        recommendation, preferences = learning_service.get_historical_recommendations(
            team=perf.team,
            score=perf.evaluation.score,
            grade=perf.evaluation.grade,
            root_cause=root_kpi,
            default_suggestion=default_suggest
        )

        return StandardResponse(
            success=True,
            message="Recommendation calculated successfully",
            data={
                "recommendation": recommendation,
                "preferences": preferences
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to calculate recommendations: {str(e)}")


@router.get("/planning", response_model=StandardResponse)
async def get_planning_categories(
    month: str = Query(...),
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        categories = planning_service.classify_all(month)
        flat_categories = {}
        for cat, recs in categories.items():
            flat_categories[cat] = [serialize_performance_record(r) for r in recs]

        return StandardResponse(
            success=True,
            message=f"Classified planning categories for {month}",
            data=flat_categories
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to compile planning lists: {str(e)}")


@router.get("/insights", response_model=StandardResponse)
async def get_insights(
    month: str = Query(...),
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        insights = insights_service.generate_insights(month)
        return StandardResponse(
            success=True,
            message="Insights compiled successfully",
            data=insights
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to compile executive insights: {str(e)}")


@router.get("/settings/weights", response_model=StandardResponse)
async def get_weights():
    try:
        weights = weights_repo.get_all()
        return StandardResponse(success=True, message="KPI Weights retrieved", data=[w.model_dump() for w in weights])
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed: {str(e)}")


@router.post("/settings/weights", response_model=StandardResponse)
async def update_weights(
    payload: KPIWeight,
    role: str = Depends(require_role(["Admin"]))
):
    try:
        weights_repo.save(payload)
        return StandardResponse(success=True, message="KPI Weights updated", data=payload.model_dump())
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed: {str(e)}")


@router.get("/settings/targets", response_model=StandardResponse)
async def get_targets():
    try:
        targets = targets_repo.get_all()
        return StandardResponse(success=True, message="KPI Targets retrieved", data=[t.model_dump() for t in targets])
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed: {str(e)}")


@router.post("/settings/targets", response_model=StandardResponse)
async def update_targets(
    payload: Target,
    role: str = Depends(require_role(["Admin"]))
):
    try:
        targets_repo.save(payload)
        
        # Recalculate stored performance records for this team
        records = performance_repo.get_all()
        updated_records = []
        for r in records:
            if r.team == payload.team:
                # Recompute performance score and achievements
                score, grade, achievements, weights_used = kpi_service.calculate_performance(r.team, r.raw_data)
                
                # Update achievements
                r.achievement.booking_ach = achievements.get("Booking", 0.0)
                r.achievement.attend_ach = achievements.get("Attend", 0.0)
                r.achievement.quality_ach = achievements.get("Quality", 0.0)
                r.achievement.aht_ach = achievements.get("AHT", 0.0)
                r.achievement.reachability_ach = achievements.get("Other", 0.0) if r.team == "Outbound" else 0.0
                r.achievement.abandon_ach = achievements.get("Other", 0.0) if r.team in ["Inbound", "Inbound UAE"] else 0.0
                r.achievement.rejection_ach = achievements.get("Rejection", 0.0)
                r.achievement.initial_error_ach = achievements.get("InitialError", 0.0)
                r.achievement.submission_ach = achievements.get("Submission", 0.0)
                
                # Update actual metrics (in case we need to recalculate them too)
                r.actual.booking_rate = float(r.raw_data.get("A.Booking%", 0.0))
                r.actual.attend_rate = float(r.raw_data.get("A.Attend%", 0.0))
                r.actual.abandon_rate = float(r.raw_data.get("A.AbandonRate%", 0.0))
                r.actual.reachability_rate = float(r.raw_data.get("A.Reachability%", 0.0))
                r.actual.rejection_rate = float(r.raw_data.get("IPInitialRejection%", 0.0))
                r.actual.initial_error_rate = float(r.raw_data.get("Error%", 0.0))
                r.actual.submission_rate = float(r.raw_data.get("NumberApprovalwithin48hrs", 0.0))
                r.actual.quality_rate = float(r.raw_data.get("A.QualityScore", 0.0))
                r.actual.utz_rate = float(r.raw_data.get("A.UTZ%", 0.0))
                
                # Update evaluation
                r.evaluation.score = score
                r.evaluation.grade = grade
                
                # Update root cause and suggested action
                from services.analysis_service import AnalysisService
                analysis_service = AnalysisService(targets_repo)
                root_cause = analysis_service.run_root_cause_analysis(r.team, achievements, weights_used, r.raw_data)
                suggested_action = analysis_service.generate_suggested_action(score, r.evaluation.suggested_action == "Probation Monitoring", root_cause)
                r.evaluation.root_cause = root_cause
                r.evaluation.suggested_action = suggested_action
                
                updated_records.append(r)
            else:
                updated_records.append(r)
        performance_repo.save_all(updated_records)
        
        return StandardResponse(success=True, message="KPI Targets updated and all performance records recalculated", data=payload.model_dump())
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed: {str(e)}")


@router.get("/team-actions", response_model=StandardResponse)
async def get_team_action(
    team_id: str = Query(...),
    month: str = Query(...)
):
    try:
        action_repo = JSONTeamActionsRepository()
        act = action_repo.get_action(team_id, month)
        return StandardResponse(
            success=True,
            message="Team action retrieved successfully",
            data=act.model_dump() if act else None
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed: {str(e)}")


@router.post("/team-actions", response_model=StandardResponse)
async def save_team_action(
    payload: Dict[str, str],
    role: str = Depends(require_role(["Admin"]))
):
    try:
        team_id = payload.get("team_id", "")
        month = payload.get("month", "")
        overall_action = payload.get("overall_action", "")
        if not team_id or not month:
            raise HTTPException(status_code=400, detail="team_id and month are required")
        
        action_repo = JSONTeamActionsRepository()
        act = TeamAction(
            team_id=team_id,
            month=month,
            overall_action=overall_action,
            updated_at=datetime.datetime.now().isoformat(),
            updated_by="Admin"
        )
        action_repo.save(act)
        return StandardResponse(
            success=True,
            message="Team action saved successfully",
            data=act.model_dump()
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed: {str(e)}")


@router.get("/reports/export")
async def export_report(
    month: str = Query("All"),
    team: str = Query("All"),
    format: str = Query("excel"),
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        records = performance_repo.get_all()
        if month != "All":
            records = [r for r in records if r.month == month]
        if team != "All":
            records = [r for r in records if r.team == team]

        if format.lower() == "csv":
            file_data = ReportExporter.export_to_csv(records)
            media_type = "text/csv"
            filename = f"PMS_Report_{month}_{team}.csv"
        else:
            file_data = ReportExporter.export_to_excel(records)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"PMS_Report_{month}_{team}.xlsx"

        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/uploads", response_model=StandardResponse)
async def get_upload_history(
    role: str = Depends(require_role(["Admin"]))
):
    try:
        records = uploads_repo.get_all()
        records.sort(key=lambda x: x.uploaded_at or "", reverse=True)
        return StandardResponse(
            success=True,
            message="Retrieved upload history successfully",
            data=[r.model_dump() for r in records]
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to fetch uploads: {str(e)}")


@router.post("/upload-pms", response_model=StandardResponse)
async def upload_pms_file(
    file: UploadFile = File(...),
    role: str = Depends(require_role(["Admin"]))
):
    try:
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="Only excel files accepted.")

        contents = await file.read()
        excel_file = excel_processor.load_excel(contents)
        
        # Save upload audit record
        upload_rec = UploadRecord(
            id=str(uuid.uuid4()),
            filename=file.filename,
            uploaded_at=datetime.datetime.now().isoformat(),
            uploaded_by="Admin"
        )
        uploads_repo.save(upload_rec)

        # Parse sheets
        inbound_df = excel_processor.process_sheet_inbound(excel_file)
        outbound_df = excel_processor.process_sheet_outbound(excel_file)
        inbound_uae_df = excel_processor.process_sheet_inbound_uae(excel_file)
        preapprovals_df = excel_processor.process_sheet_preapprovals(excel_file)

        # Map to unified models and save
        all_new_records = []
        all_new_employees = []

        sheet_mappings = [
            ("Inbound", inbound_df, "EmployeeID", "EnglishName"),
            ("Outbound", outbound_df, "SGHCode", "EnglishName"),
            ("Inbound UAE", inbound_uae_df, "HRID", "AgentName"),
            ("Pre-Approvals IP Offshore", preapprovals_df, "HRID", "AgentName")
        ]

        for team_name, df, id_col, name_col in sheet_mappings:
            for _, row in df.iterrows():
                name = str(row.get(name_col, "")).strip()
                emp_id = str(row.get(id_col, "")).strip()
                # Clean employee id (remove .0 from floats)
                if emp_id.endswith(".0"):
                    emp_id = emp_id[:-2]
                
                if not name or name.lower() == "total" or not emp_id or emp_id.lower() == "nan":
                    continue

                date_val = row.get("Date")
                month = "Unknown"
                if isinstance(date_val, (pd.Timestamp, datetime.datetime)):
                    month = date_val.strftime('%B')
                
                # Check status
                status = str(row.get("Status", "Active"))
                is_new = row.get("Is_New", False)

                # Save Employee record
                employee = Employee(
                    id=emp_id,
                    name=name,
                    team=team_name,
                    status=status
                )
                all_new_employees.append(employee)

                # Fetch AHT raw
                aht_val = row.get("AHT") or row.get("A.AHT") or row.get("A.AHT.1") or "00:00:00"
                if isinstance(aht_val, datetime.time):
                    aht_raw = aht_val.strftime("%H:%M:%S")
                elif isinstance(aht_val, str):
                    aht_raw = aht_val
                elif isinstance(aht_val, (int, float)):
                    from utils.helpers import convert_aht_to_minutes, format_minutes_to_hhmmss
                    aht_raw = format_minutes_to_hhmmss(convert_aht_to_minutes(aht_val))
                else:
                    aht_raw = "00:00:00"

                # Standard calls mapping
                calls = CallsData(
                    inbound=safe_int(row.get("InboundCalls", 0)) if "InboundCalls" in df.columns else safe_int(row.get("InboundCalls ", 0)) if "InboundCalls " in df.columns else 0,
                    outbound=safe_int(row.get("OutboundCalls", 0)) if "OutboundCalls" in df.columns else 0,
                    total_handled=safe_int(row.get("TotalHandledCalls", 0)) if "TotalHandledCalls" in df.columns else (safe_int(row.get("Reached", 0)) if team_name == "Outbound" else 0),
                    abandoned=safe_int(row.get("AbandonedCalls", 0)) if "AbandonedCalls" in df.columns else 0,
                    aht_raw=aht_raw
                )

                # Geo mapping
                geo_bookings = GeoBreakdown(
                    dubai=safe_int(row.get("Dubai_Booking") or row.get("Dubai_Booking") or 0),
                    sharjah=safe_int(row.get("Sharjah_Booking") or 0),
                    ajman=safe_int(row.get("Ajman_Booking") or 0),
                    clinics=safe_int(row.get("Clinics_Booking") or row.get("clinics_Booking") or row.get("Clinics_Booking") or 0),
                )
                geo_attended = GeoBreakdown(
                    dubai=safe_int(row.get("Dubai_Attend") or 0),
                    sharjah=safe_int(row.get("Sharjah_Attend") or 0),
                    ajman=safe_int(row.get("Ajman_Attend") or 0),
                    clinics=safe_int(row.get("Clinics_Attend") or row.get("clinics_Attend") or row.get("clinics.Attend") or row.get("Clinics.Attend") or 0),
                )
                geo = GeoData(bookings=geo_bookings, attended=geo_attended)

                # Actual metrics mapping
                actual = ActualMetrics(
                    booking_rate=safe_float(row.get("A.Booking%", 0.0)),
                    attend_rate=safe_float(row.get("A.Attend%", 0.0)),
                    abandon_rate=safe_float(row.get("A.AbandonRate%", 0.0)),
                    reachability_rate=safe_float(row.get("A.Reachability%", 0.0)),
                    rejection_rate=safe_float(row.get("IPInitialRejection%", 0.0)),
                    initial_error_rate=safe_float(row.get("Error%", 0.0)),
                    submission_rate=safe_float(row.get("NumberApprovalwithin48hrs", 0.0)),
                    quality_rate=safe_float(row.get("A.QualityScore", 0.0)),
                    utz_rate=safe_float(row.get("A.UTZ%", 0.0))
                )

                # Run KPI scoring engine
                score, grade, achievements, weights_used = kpi_service.calculate_performance(team_name, row.to_dict())

                # Populate achievements model
                ach = AchievementMetrics(
                    booking_ach=achievements.get("Booking", 0.0),
                    attend_ach=achievements.get("Attend", 0.0),
                    quality_ach=achievements.get("Quality", 0.0),
                    aht_ach=achievements.get("AHT", 0.0),
                    reachability_ach=achievements.get("Other", 0.0) if team_name == "Outbound" else 0.0,
                    abandon_ach=achievements.get("Other", 0.0) if team_name in ["Inbound", "Inbound UAE"] else 0.0,
                    rejection_ach=achievements.get("Rejection", 0.0),
                    initial_error_ach=achievements.get("InitialError", 0.0),
                    submission_ach=achievements.get("Submission", 0.0)
                )

                # Run Root Cause Analysis Engine
                root_cause = analysis_service.run_root_cause_analysis(team_name, achievements, weights_used, row.to_dict())

                # Run Suggested Action Engine
                suggested_action = analysis_service.generate_suggested_action(score, is_new, root_cause)

                # Fetch historical manager notes and corrective action
                note_rec = notes_repo.get_note(emp_id, month)
                action_rec = actions_repo.get_latest_by_employee_and_month(emp_id, month)

                # Create active evaluation structure
                evaluation = EvaluationData(
                    score=score,
                    grade=grade,
                    root_cause=root_cause,
                    suggested_action=suggested_action,
                    corrective_action=action_rec.manager_action if action_rec else None,
                    manager_notes=note_rec.notes if note_rec else None
                )

                record = PerformanceRecord(
                    id=f"{emp_id}_{month}",
                    employee_id=emp_id,
                    employee_name=name,
                    team=team_name,
                    month=month,
                    calls=calls,
                    geo=geo,
                    actual=actual,
                    achievement=ach,
                    evaluation=evaluation,
                    upload_id=upload_rec.id,
                    raw_data={str(k): safe_value(v) for k, v in row.to_dict().items()}
                )
                all_new_records.append(record)

        # Save all to repositories
        employee_repo.save_all(all_new_employees)
        performance_repo.save_all(all_new_records)

        # Post-Processing: Run Planning classifications and Trends updates
        # Update trends for all saved records based on chronological history
        updated_records = []
        for r in all_new_records:
            history = performance_repo.get_all()
            emp_history = [h for h in history if h.employee_id == r.employee_id]
            from services.planning_service import MONTH_ORDER
            emp_history.sort(key=lambda x: MONTH_ORDER.get(x.month, 0))
            
            # Find current index
            curr_idx = -1
            for i, h in enumerate(emp_history):
                if h.month == r.month:
                    curr_idx = i
                    break

            if curr_idx >= 0:
                trend_status = trend_service.calculate_trends(emp_history, curr_idx)
                r.evaluation.trend_status = trend_status

            # Calculate planning category list
            planning_lists = planning_service.classify_all(r.month)
            r.evaluation.planning_category = []
            for cat, recs in planning_lists.items():
                if any(x.id == r.id for x in recs):
                    r.evaluation.planning_category.append(cat)

            updated_records.append(r)

        performance_repo.save_all(updated_records)

        return StandardResponse(
            success=True,
            message="PMS Excel uploaded and processed successfully",
            data={
                "records_imported": len(all_new_records),
                "employees_imported": len(all_new_employees)
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return StandardResponse(success=False, message=f"Failed to upload and process Excel file: {str(e)}")

@router.delete("/uploads/{upload_id}", response_model=StandardResponse)
async def delete_upload(
    upload_id: str,
    role: str = Depends(require_role(["Admin"]))
):
    try:
        uploads = uploads_repo.get_all()
        target_upload = None
        for u in uploads:
            if u.id == upload_id:
                target_upload = u
                break
        
        if not target_upload:
            raise HTTPException(status_code=404, detail="Upload record not found")

        affected_employee_ids = performance_repo.delete_by_upload_id(upload_id)

        for emp_id in affected_employee_ids:
            emp_history = [h for h in performance_repo.get_all() if h.employee_id == emp_id]
            from services.planning_service import MONTH_ORDER
            emp_history.sort(key=lambda x: MONTH_ORDER.get(x.month, 0))
            
            for idx, r in enumerate(emp_history):
                trend_status = trend_service.calculate_trends(emp_history, idx)
                r.evaluation.trend_status = trend_status
                
                planning_lists = planning_service.classify_all(r.month)
                r.evaluation.planning_category = []
                for cat, recs in planning_lists.items():
                    if any(x.id == r.id for x in recs):
                        r.evaluation.planning_category.append(cat)
            
            performance_repo.save_all(emp_history)

        success = uploads_repo.delete_by_id(upload_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete upload log from repository")

        return StandardResponse(
            success=True,
            message=f"Successfully deleted upload history and {len(affected_employee_ids)} affected agent records recalculated."
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        return StandardResponse(success=False, message=f"Failed to delete upload: {str(e)}")

def safe_value(val):
    import math
    if pd.isna(val):
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    return str(val)

# User Management routes
@router.get("/users", response_model=StandardResponse)
async def get_users(
    role: str = Depends(require_role(["Admin"]))
):
    try:
        users = user_repo.get_all()
        return StandardResponse(
            success=True,
            message="Users retrieved successfully",
            data=[u.model_dump() for u in users]
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to fetch users: {str(e)}")

@router.post("/users", response_model=StandardResponse)
async def create_user(
    payload: UserRecord,
    role: str = Depends(require_role(["Admin"]))
):
    try:
        user_repo.save(payload)
        return StandardResponse(
            success=True,
            message="User created successfully",
            data=payload.model_dump()
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to create user: {str(e)}")

@router.delete("/users/{user_id}", response_model=StandardResponse)
async def delete_user_route(
    user_id: str,
    role: str = Depends(require_role(["Admin"]))
):
    try:
        success = user_repo.delete(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return StandardResponse(
            success=True,
            message="User deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to delete user: {str(e)}")

# Corrective Actions route (All corrective actions)
@router.get("/corrective-actions", response_model=StandardResponse)
async def get_all_corrective_actions(
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        actions = actions_repo.get_history()
        return StandardResponse(
            success=True,
            message="Retrieved all corrective actions successfully",
            data=[a.model_dump() for a in actions]
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to fetch corrective actions: {str(e)}")

@router.post("/users/login", response_model=StandardResponse)
async def login_user(payload: LoginPayload):
    try:
        users = user_repo.get_all()
        found = None
        for u in users:
            if u.username.lower() == payload.username.strip().lower() and u.password == payload.password:
                found = u
                break
        if not found:
            return StandardResponse(success=False, message="Invalid username or password")
        
        user_data = found.model_dump()
        user_data.pop("password", None)
        return StandardResponse(
            success=True,
            message="Login successful",
            data=user_data
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Login failed: {str(e)}")
