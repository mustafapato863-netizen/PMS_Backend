from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import datetime
import logging
import time

from api.dependencies import uploads_repo, performance_repo, trend_service, planning_service
from api.middleware.rbac_middleware import require_permission
from services.seeding_service import DatabaseSeeder
from services.cache_invalidation_service import CacheInvalidationService
from models.schemas import StandardResponse

logger = logging.getLogger(__name__)

def _warm_team_caches() -> None:
    """Pre-compute and cache team performance aggregates after data changes."""
    try:
        from services.cache_service import CacheService
        all_records = performance_repo.get_all()

        teams_months = set()
        for r in all_records:
            month = getattr(r, "month", None)
            team = getattr(r, "team", None)
            if month and team:
                teams_months.add((team, month))

        if not teams_months:
            return

        for team_name, month in teams_months:
            team_records = [r for r in all_records if r.team == team_name and r.month == month]
            scores = [r.evaluation.score for r in team_records if r.evaluation and r.evaluation.score]
            aggregated = {
                "total_records": len(scores),
                "average_score": sum(scores) / len(scores) if scores else 0.0,
                "max_score": max(scores) if scores else 0.0,
                "min_score": min(scores) if scores else 0.0
            }
            CacheService.set_team_performance_cache(team_name, month, 2026, aggregated)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Cache warming failed (non-critical): {e}")


router = APIRouter()

@router.get("/", response_model=StandardResponse)
async def get_upload_history(
    _user=Depends(require_permission("view_reports"))
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

@router.post("/pms", response_model=StandardResponse)
async def upload_pms_file(
    file: UploadFile = File(...),
    _user=Depends(require_permission("upload_data"))
):
    try:
        started_at = time.perf_counter()
        upload_filename = file.filename
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="Only excel files accepted.")

        contents = await file.read()
        seeder = DatabaseSeeder()
        result = seeder.process_uploaded_file(file.filename, contents)

        # Invalidate all caches and warm team aggregates
        CacheInvalidationService.flush_all()
        _warm_team_caches()

        # Emit file upload success notification
        from services.socket_service import SocketNotificationService
        teams_list = result.get("teams", []) if isinstance(result, dict) else []
        teams_str = ", ".join(teams_list) if teams_list else "All Teams"
        await SocketNotificationService.notify_file_upload(
            filename=file.filename,
            team_name=teams_str,
            teams=teams_list,
            status="success"
        )
        logger.info(
            "upload processed",
            extra={"upload_filename": upload_filename, "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 2)},
        )

        return StandardResponse(
            success=True,
            message="PMS Excel uploaded and processed successfully",
            data=result
        )
    except Exception as e:
        report = getattr(e, "report", None) or {}
        teams_list = report.get("detected_teams") or report.get("attempted_teams") or report.get("teams") or []
        payload = {
            "filename": file.filename,
            "team_name": "All Teams",
            "status": "failed",
            "detected_teams": report.get("detected_teams", teams_list),
            "attempted_teams": report.get("attempted_teams", teams_list),
            "persisted_teams": report.get("persisted_teams", []),
            "failed_teams": report.get("failed_teams", []),
        }
        # Emit file upload failure notification
        from services.socket_service import SocketNotificationService
        await SocketNotificationService.notify_file_upload(
            filename=file.filename,
            team_name="All Teams",
            teams=teams_list,
            status="failed",
            details=payload,
        )
        logger.warning(
            "upload failed",
            extra={"upload_filename": file.filename, "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 2)},
        )
        return StandardResponse(success=False, message=f"Failed to upload and process Excel file: {str(e)}", data=payload)

@router.delete("/{upload_id}", response_model=StandardResponse)
async def delete_upload(
    upload_id: str,
    _user=Depends(require_permission("delete_performance"))
):
    try:
        uploads = uploads_repo.get_all()
        target_upload = next((u for u in uploads if u.id == upload_id), None)
        
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

        CacheInvalidationService.flush_all()

        return StandardResponse(
            success=True,
            message=f"Successfully deleted upload history and {len(affected_employee_ids)} affected agent records recalculated."
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to delete upload: {str(e)}")
