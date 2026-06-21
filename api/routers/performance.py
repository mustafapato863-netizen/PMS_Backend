from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
import io
from typing import List
from datetime import datetime

from api.dependencies import performance_repo, planning_service, insights_service, serialize_performance_record, require_role
from models.schemas import StandardResponse
from exports.report_exporter import ReportExporter

router = APIRouter(prefix="/performance", tags=["Performance"])

@router.get("", response_model=StandardResponse)
def get_all_records(
    team: str = Query(None, alias="team"),
    month: str = Query(None),
):
    try:
        records = performance_repo.get_all()
        if team:
            records = [r for r in records if r.team == team]
        if month:
            records = [r for r in records if r.month == month]

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
    team: str = Query(None, alias="team"),
    month: str = Query(None),
):
    try:
        records = performance_repo.get_all()
        if team:
            records = [r for r in records if r.team == team]
        if month:
            records = [r for r in records if r.month == month]

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
def get_employee_history(emp_id: str):
    try:
        records = performance_repo.get_all()
        emp_records = [r for r in records if str(r.employee_id) == emp_id]
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
def get_team_yearly_records(team_name: str):
    try:
        records = performance_repo.get_all()
        team_records = [r for r in records if r.team == team_name]

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
    grade: str = Query(...),
    month: str = Query(...),
):
    try:
        if not month:
            raise HTTPException(status_code=400, detail="month is required")

        records = performance_repo.get_all()
        filtered = [r for r in records if r.team == team_name and r.evaluation.grade == grade and r.month == month]

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
    status: str = Query(...),
    month: str = Query(...),
):
    try:
        if not month:
            raise HTTPException(status_code=400, detail="month is required")

        records = performance_repo.get_all()
        status_val = status.lower()
        filtered = [r for r in records if r.team == team_name and r.month == month]
        if status_val == "exceeds":
            filtered = [r for r in filtered if r.evaluation.score >= 90]
        elif status_val == "meets":
            filtered = [r for r in filtered if 70 <= r.evaluation.score < 90]
        elif status_val == "below":
            filtered = [r for r in filtered if r.evaluation.score < 70]

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
def get_insights(
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


@router.get("/export", response_class=StreamingResponse)
def export_report(
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
