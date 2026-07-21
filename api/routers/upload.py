from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import datetime
import logging
import time
from sqlalchemy.orm import Session

from config.database import get_db
from api.dependencies import (
    uploads_repo,
    performance_repo,
    trend_service,
    planning_service,
    clear_serialization_cache,
)
from api.middleware.rbac_middleware import require_permission
from services.seeding_service import DatabaseSeeder
from services.cache_invalidation_service import CacheInvalidationService
from models.schemas import StandardResponse
from services.upload_security import read_validated_excel

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
            year = getattr(r, "year", None) or 2026
            if month and team:
                teams_months.add((team, month, year))

        if not teams_months:
            return

        for team_name, month, year in teams_months:
            team_records = [
                r for r in all_records
                if r.team == team_name and r.month == month and (r.year or 2026) == year
            ]
            scores = [r.evaluation.score for r in team_records if r.evaluation and r.evaluation.score]
            by_position = {}
            positions = sorted({
                r.position
                for r in team_records
                if isinstance(getattr(r, "position", None), str) and r.position
            })
            for position in positions:
                position_scores = [
                    r.evaluation.score
                    for r in team_records
                    if r.position == position and r.evaluation and r.evaluation.score is not None
                ]
                by_position[position] = {
                    "total_records": len(position_scores),
                    "average_score": sum(position_scores) / len(position_scores) if position_scores else 0.0,
                    "max_score": max(position_scores) if position_scores else 0.0,
                    "min_score": min(position_scores) if position_scores else 0.0,
                }
            aggregated = {
                "total_records": len(scores),
                "average_score": sum(scores) / len(scores) if scores else 0.0,
                "max_score": max(scores) if scores else 0.0,
                "min_score": min(scores) if scores else 0.0,
                "by_position": by_position,
            }
            CacheService.set_team_performance_cache(team_name, month, year, aggregated)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Cache warming failed (non-critical): {e}")


router = APIRouter()

@router.get("/", response_model=StandardResponse)
async def get_upload_history(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports"))
):
    try:
        from models.models import UploadLog
        records = db.query(UploadLog).order_by(UploadLog.uploaded_at.desc()).all()
        return StandardResponse(
            success=True,
            message="Retrieved upload history successfully",
            data=[
                {
                    "id": str(r.id),
                    "filename": "Unknown",  # filename not stored in upload_log
                    "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                    "uploaded_by": str(r.uploaded_by_user_id) if r.uploaded_by_user_id else "Admin",
                    "status": r.status,
                }
                for r in records
            ]
        )
    except Exception as e:
        logger.exception("Failed to fetch upload history")
        return StandardResponse(success=False, message="Failed to fetch upload history.")

@router.post("/pms", response_model=StandardResponse)
async def upload_pms_file(
    file: UploadFile = File(...),
    dry_run: bool = False,
    _user=Depends(require_permission("upload_data"))
):
    try:
        started_at = time.perf_counter()
        upload_filename = file.filename
        contents = await read_validated_excel(file)
        seeder = DatabaseSeeder()
        result = (
            seeder.process_uploaded_file(file.filename, contents, dry_run=True)
            if dry_run
            else seeder.process_uploaded_file(file.filename, contents)
        )

        if not dry_run:
            CacheInvalidationService.flush_all()
            clear_serialization_cache()
            _warm_team_caches()

        teams_list = result.get("teams", []) if isinstance(result, dict) else []
        if not dry_run:
            from services.socket_service import SocketNotificationService
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
            message=(
                "PMS Excel preflight completed successfully"
                if dry_run
                else "PMS Excel uploaded and processed successfully"
            ),
            data=result
        )
    except HTTPException:
        raise
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
        if not dry_run:
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
        logger.exception("Unexpected upload processing failure")
        status_code = getattr(e, "status_code", 500)
        error_type = type(e).__name__
        if error_type in ("UploadProcessingError", "ConfigurationError") or status_code == 422:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": str(e),
                    "errors": getattr(e, "errors", report.get("validation_errors", [])),
                    "report": report,
                },
            ) from e
        raise HTTPException(status_code=500, detail=f"Upload processing failed: {type(e).__name__}: {str(e)[:500]}") from e

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
        logger.exception("Failed to delete upload")
        return StandardResponse(success=False, message="Failed to delete upload.")
