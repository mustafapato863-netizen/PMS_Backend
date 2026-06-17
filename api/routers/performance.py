from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
import io
from typing import List

from api.dependencies import performance_repo, planning_service, insights_service, serialize_performance_record, require_role
from models.schemas import StandardResponse
from exports.report_exporter import ReportExporter

router = APIRouter()

@router.get("/performance", response_model=StandardResponse)
async def get_performance(
    month: str = Query("All"),
    team: str = Query("All")
):
    try:
        records = performance_repo.get_all()
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
