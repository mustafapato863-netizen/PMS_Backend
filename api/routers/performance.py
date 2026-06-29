from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
import io
from typing import List
from datetime import datetime

from api.dependencies import (
    performance_repo,
    planning_service,
    insights_service,
    serialize_performance_record,
    require_role,
    get_current_user_scope,
    filter_records_by_scope,
    user_can_access_team,
)
from config.database import get_db
from sqlalchemy.orm import Session
from models.schemas import StandardResponse
from exports.report_exporter import ReportExporter
from repositories.performance_repository import PerformanceRepository as SQLPerformanceRepository
from models.models import PerformanceRecord
from utils.performance_levels import normalize_performance_level

router = APIRouter(prefix="/performance", tags=["Performance"])


def _level_filter(value: str | None) -> str | None:
    try:
        normalized = normalize_performance_level(value, allow_all=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return None if normalized == "All" else normalized


def _get_dashboard_records(
    db: Session,
    team: str | None = None,
    month: str | None = None,
    employee_id: str | None = None,
    grade: str | None = None,
    status: str | None = None,
    performance_level: str | None = None,
):
    sql_repo = SQLPerformanceRepository(db, PerformanceRecord)
    try:
        keys = sql_repo.get_dashboard_record_keys(
            team=team,
            month=month,
            employee_id=employee_id,
            grade=grade,
            status=status,
            performance_level=performance_level,
        )
    except Exception:
        keys = []

    if keys:
        matched = performance_repo.get_filtered_by_keys(set(keys))
        if performance_level:
            matched = [record for record in matched if record.performance_level == performance_level]
        if matched:
            return matched

    return performance_repo.get_filtered(
        team=team,
        month=month,
        employee_id=employee_id,
        grade=grade,
        status=status,
        performance_level=performance_level,
    )

@router.get("", response_model=StandardResponse)
def get_all_records(
    request: Request,
    db: Session = Depends(get_db),
    team: str = Query(None, alias="team"),
    month: str = Query(None),
    performance_level: str = Query(None),
):
    try:
        scope = get_current_user_scope(db, request)
        if team and not user_can_access_team(scope, team):
            raise HTTPException(status_code=403, detail="Access denied for this team")

        records = _get_dashboard_records(db, team=team, month=month, performance_level=_level_filter(performance_level))
        records = filter_records_by_scope(records, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} performance records",
            data=[serialize_performance_record(r) for r in records]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch performance records: {str(e)}"
        )


@router.get("/records", response_model=StandardResponse)
def get_monthly_records(
    request: Request,
    db: Session = Depends(get_db),
    team: str = Query(None, alias="team"),
    month: str = Query(None),
    performance_level: str = Query(None),
):
    try:
        scope = get_current_user_scope(db, request)
        if team and not user_can_access_team(scope, team):
            raise HTTPException(status_code=403, detail="Access denied for this team")

        records = _get_dashboard_records(db, team=team, month=month, performance_level=_level_filter(performance_level))
        records = filter_records_by_scope(records, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} performance records",
            data=[serialize_performance_record(r) for r in records]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch performance records: {str(e)}"
        )


@router.get("/employee/{emp_id}", response_model=StandardResponse)
def get_employee_history(emp_id: str, request: Request, db: Session = Depends(get_db), performance_level: str = Query(None)):
    try:
        scope = get_current_user_scope(db, request)
        records = _get_dashboard_records(db, employee_id=emp_id, performance_level=_level_filter(performance_level))
        records = filter_records_by_scope(records, scope)
        emp_records = records
        from services.planning_service import MONTH_ORDER
        emp_records.sort(key=lambda x: MONTH_ORDER.get(x.month, 0))

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(emp_records)} performance records for employee",
            data=[serialize_performance_record(r) for r in emp_records]
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch employee performance history: {str(e)}"
        )


@router.get("/team/{team_name}", response_model=StandardResponse)
def get_team_yearly_records(team_name: str, request: Request, db: Session = Depends(get_db), performance_level: str = Query(None)):
    try:
        scope = get_current_user_scope(db, request)
        if not user_can_access_team(scope, team_name):
            raise HTTPException(status_code=403, detail="Access denied for this team")
        team_records = _get_dashboard_records(db, team=team_name, performance_level=_level_filter(performance_level))
        team_records = filter_records_by_scope(team_records, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(team_records)} performance records for team",
            data=[serialize_performance_record(r) for r in team_records]
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch team performance records: {str(e)}"
        )


@router.get("/grade/{team_name}", response_model=StandardResponse)
def get_by_grade(
    team_name: str,
    request: Request,
    db: Session = Depends(get_db),
    grade: str = Query(...),
    month: str = Query(...),
    performance_level: str = Query(None),
):
    try:
        if not month:
            raise HTTPException(status_code=400, detail="month is required")

        scope = get_current_user_scope(db, request)
        if not user_can_access_team(scope, team_name):
            raise HTTPException(status_code=403, detail="Access denied for this team")
        filtered = _get_dashboard_records(db, team=team_name, month=month, grade=grade, performance_level=_level_filter(performance_level))
        filtered = filter_records_by_scope(filtered, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(filtered)} records with grade {grade}",
            data=[serialize_performance_record(r) for r in filtered]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch records by grade: {str(e)}"
        )


@router.get("/status/{team_name}", response_model=StandardResponse)
def get_by_status(
    team_name: str,
    request: Request,
    db: Session = Depends(get_db),
    status: str = Query(...),
    month: str = Query(...),
    performance_level: str = Query(None),
):
    try:
        if not month:
            raise HTTPException(status_code=400, detail="month is required")

        scope = get_current_user_scope(db, request)
        if not user_can_access_team(scope, team_name):
            raise HTTPException(status_code=403, detail="Access denied for this team")
        filtered = _get_dashboard_records(db, team=team_name, month=month, status=status, performance_level=_level_filter(performance_level))
        filtered = filter_records_by_scope(filtered, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(filtered)} records with status {status}",
            data=[serialize_performance_record(r) for r in filtered]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch records by status: {str(e)}"
        )


@router.get("/planning", response_model=StandardResponse)
def get_planning_categories(
    month: str = Query(...),
    performance_level: str = Query(None),
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        categories = planning_service.classify_all(month, _level_filter(performance_level))
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
def get_insights(
    month: str = Query(...),
    performance_level: str = Query(None),
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        insights = insights_service.generate_insights(month, _level_filter(performance_level))
        return StandardResponse(
            success=True,
            message="Insights compiled successfully",
            data=insights
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to compile executive insights: {str(e)}")


@router.get("/export", response_class=StreamingResponse)
def export_report(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query("All"),
    team: str = Query("All"),
    format: str = Query("excel"),
    performance_level: str = Query(None),
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        scope = get_current_user_scope(db, request)
        if team != "All":
            if not user_can_access_team(scope, team):
                raise HTTPException(status_code=403, detail="Access denied for this team")
        records = _get_dashboard_records(
            db,
            team=None if team == "All" else team,
            month=None if month == "All" else month,
            performance_level=_level_filter(performance_level),
        )
        records = filter_records_by_scope(records, scope)

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
