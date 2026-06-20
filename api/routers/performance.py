from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
import io
from typing import List
from datetime import datetime

from api.dependencies import performance_repo, planning_service, insights_service, serialize_performance_record, require_role
from models.schemas import StandardResponse
from exports.report_exporter import ReportExporter
from services.performance_service import PerformanceService

router = APIRouter(prefix="/performance", tags=["Performance"])

@router.get("", response_model=StandardResponse)
async def get_monthly_records_root(
    team_id: str = Query(None),
    month: str = Query(None),
    year: int = Query(None)
):
    """
    Alias endpoint for get_monthly_records matching the frontend root query path.
    """
    return await get_monthly_records(team_id, month, year)


@router.get("/records", response_model=StandardResponse)
async def get_monthly_records(
    team_id: str = Query(None),
    month: str = Query(None),
    year: int = Query(None)
):
    """
    Get monthly performance records for a team.
    
    Args:
        team_id: Team ID (optional)
        month: Month name (optional)
        year: Year (optional, defaults to current year)
        
    Returns:
        List of performance records
    """
    try:
        if year is None:
            year = datetime.now().year
        
        if not team_id or not month:
            raise HTTPException(status_code=400, detail="team_id and month are required")
        
        records = PerformanceService.get_monthly_records(team_id, month, year)
        
        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} performance records",
            data=records
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch performance records: {str(e)}"
        )


@router.get("/employee/{emp_id}/{year}", response_model=StandardResponse)
async def get_employee_history(emp_id: str, year: int):
    """
    Get performance history for an employee in a specific year.
    
    Args:
        emp_id: Employee ID
        year: Year
        
    Returns:
        List of performance records for employee
    """
    try:
        records = PerformanceService.get_employee_history(emp_id, year)
        
        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} performance records for employee",
            data=records
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch employee performance history: {str(e)}"
        )


@router.get("/team/{team_id}/{year}", response_model=StandardResponse)
async def get_team_yearly_records(team_id: str, year: int):
    """
    Get yearly performance records for a team.
    
    Args:
        team_id: Team ID
        year: Year
        
    Returns:
        List of performance records for team
    """
    try:
        records = PerformanceService.get_team_yearly_records(team_id, year)
        
        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} performance records for team",
            data=records
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch team performance records: {str(e)}"
        )


@router.get("/grade/{team_id}", response_model=StandardResponse)
async def get_by_grade(
    team_id: str,
    grade: str = Query(...),
    month: str = Query(None),
    year: int = Query(None)
):
    """
    Get performance records filtered by grade.
    
    Args:
        team_id: Team ID
        grade: Grade (A, B, C, D, E)
        month: Month name (optional)
        year: Year (optional, defaults to current year)
        
    Returns:
        List of performance records
    """
    try:
        if year is None:
            year = datetime.now().year
        
        if not month:
            raise HTTPException(status_code=400, detail="month is required")
        
        records = PerformanceService.get_by_grade(team_id, grade, month, year)
        
        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} records with grade {grade}",
            data=records
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch records by grade: {str(e)}"
        )


@router.get("/status/{team_id}", response_model=StandardResponse)
async def get_by_status(
    team_id: str,
    status: str = Query(...),
    month: str = Query(None),
    year: int = Query(None)
):
    """
    Get performance records filtered by status.
    
    Args:
        team_id: Team ID
        status: Status (Exceeds, Meets, Below)
        month: Month name (optional)
        year: Year (optional, defaults to current year)
        
    Returns:
        List of performance records
    """
    try:
        if year is None:
            year = datetime.now().year
        
        if not month:
            raise HTTPException(status_code=400, detail="month is required")
        
        records = PerformanceService.get_by_status(team_id, status, month, year)
        
        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} records with status {status}",
            data=records
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to fetch records by status: {str(e)}"
        )


@router.post("/records", response_model=StandardResponse, status_code=201)
async def create_performance_record(
    employee_id: str = Query(...),
    team_id: str = Query(...),
    month: str = Query(...),
    year: int = Query(...),
    score: float = Query(...),
    grade: str = Query(...),
    status: str = Query(...),
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    """
    Create a new performance record.
    
    Args:
        employee_id: Employee ID
        team_id: Team ID
        month: Month name
        year: Year
        score: Performance score
        grade: Grade (A, B, C, D, E)
        status: Status (Exceeds, Meets, Below)
        
    Returns:
        Created performance record
    """
    try:
        success, record_dict, errors = PerformanceService.create_performance_record(
            employee_id=employee_id,
            team_id=team_id,
            month=month,
            year=year,
            score=score,
            grade=grade,
            status=status
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        
        return StandardResponse(
            success=True,
            message="Performance record created successfully",
            data=record_dict
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to create performance record: {str(e)}"
        )


@router.put("/records/{record_id}", response_model=StandardResponse)
async def update_performance_record(
    record_id: str,
    year: int = Query(...),
    score: float = Query(None),
    grade: str = Query(None),
    status: str = Query(None),
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    """
    Update a performance record.
    
    Args:
        record_id: Record ID
        year: Year (for composite key)
        score: Updated score (optional)
        grade: Updated grade (optional)
        status: Updated status (optional)
        
    Returns:
        Updated performance record
    """
    try:
        updates = {}
        if score is not None:
            updates['score'] = score
        if grade is not None:
            updates['grade'] = grade
        if status is not None:
            updates['status'] = status
        
        success, record_dict, errors = PerformanceService.update_performance_record(
            record_id=record_id,
            year=year,
            **updates
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        
        return StandardResponse(
            success=True,
            message="Performance record updated successfully",
            data=record_dict
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to update performance record: {str(e)}"
        )


@router.delete("/records/{record_id}", response_model=StandardResponse)
async def delete_performance_record(
    record_id: str,
    year: int = Query(...),
    role: str = Depends(require_role(["Admin"]))
):
    """
    Delete a performance record.
    
    Args:
        record_id: Record ID
        year: Year (for composite key)
        
    Returns:
        Deletion confirmation
    """
    try:
        success, errors = PerformanceService.delete_performance_record(record_id, year)
        
        if not success:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        
        return StandardResponse(
            success=True,
            message="Performance record deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to delete performance record: {str(e)}"
        )




@router.get("/planning", response_model=StandardResponse)
async def get_planning_categories(
    month: str = Query(...),
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    """
    Get planning categories for a month.
    
    Args:
        month: Month name
        
    Returns:
        Performance records classified by planning category
    """
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
    """
    Get executive insights for a month.
    
    Args:
        month: Month name
        
    Returns:
        Insights and analytics for the month
    """
    try:
        insights = insights_service.generate_insights(month)
        return StandardResponse(
            success=True,
            message="Insights compiled successfully",
            data=insights
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to compile executive insights: {str(e)}")
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
