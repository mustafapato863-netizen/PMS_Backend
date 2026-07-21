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
from services.employee_upload_service import EmployeeUploadService

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
        return StandardResponse(
            success=True,
            message="Retrieved upload history successfully",
            data=EmployeeUploadService(db).list_uploads(),
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
            else seeder.process_uploaded_file(
                file.filename,
                contents,
                uploaded_by_user_id=(str(_user.get("user_id")) if isinstance(_user, dict) and _user.get("user_id") else None),
                uploaded_by_name=(
                    _user.get("name") or _user.get("username") or "Admin"
                    if isinstance(_user, dict)
                    else "Admin"
                ),
            )
        )

        if not dry_run:
            CacheInvalidationService.flush_all()
            clear_serialization_cache()

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
    db: Session = Depends(get_db),
    _user=Depends(require_permission("delete_performance"))
):
    try:
        result = EmployeeUploadService(db).delete_upload(upload_id)
        if not result["found"]:
            raise HTTPException(status_code=404, detail="Upload file not found")
        CacheInvalidationService.flush_all()
        clear_serialization_cache()
        return StandardResponse(
            success=True,
            message=(
                "Successfully deleted the uploaded workbook and "
                f"{result['performance_deleted']} current performance records."
            ),
            data=result,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete upload")
        raise HTTPException(status_code=500, detail=f"Failed to delete upload: {e}") from e

from pydantic import BaseModel

class BatchDeleteRequest(BaseModel):
    upload_ids: list[str]

@router.post("/batch-delete", response_model=StandardResponse)
async def batch_delete_uploads(
    request: BatchDeleteRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("delete_performance"))
):
    try:
        result = EmployeeUploadService(db).delete_uploads(request.upload_ids)
        CacheInvalidationService.flush_all()
        clear_serialization_cache()
        
        return StandardResponse(
            success=True,
            message=(
                f"Successfully deleted {result['uploads_deleted']} uploaded workbooks and "
                f"{result['performance_deleted']} current performance records."
            ),
            data=result,
        )
    except Exception as e:
        logger.exception("Failed to batch delete uploads")
        raise HTTPException(status_code=500, detail=f"Failed to batch delete uploads: {e}") from e
