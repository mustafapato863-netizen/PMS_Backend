from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope
from api.middleware.rbac_middleware import require_permission
from config.database import get_db
from models.report_schemas import ReportConfiguration, SaveReportTemplateRequest
from models.schemas import StandardResponse
from services.report_service import (
    ReportAccessError,
    ReportNotFoundError,
    ReportService,
    ReportValidationError,
)


router = APIRouter(prefix="/reports", tags=["Reports"])


def _scope(db: Session, request: Request) -> dict:
    return require_authenticated_scope(db, request)


def _raise_report_error(exc: Exception) -> None:
    if isinstance(exc, ReportAccessError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, ReportNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ReportValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise exc


@router.get("/templates", response_model=StandardResponse)
def list_report_templates(
    _user=Depends(require_permission("view_reports")),
):
    return StandardResponse(success=True, message="Report templates retrieved", data=ReportService.templates())


@router.get("/options", response_model=StandardResponse)
def get_report_options(
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    return StandardResponse(
        success=True,
        message="Authorized report filters retrieved",
        data=ReportService(db).options(_scope(db, request)),
    )


@router.get("", response_model=StandardResponse)
def list_reports(
    request: Request,
    mine: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    data = ReportService(db).list_generated(_scope(db, request), mine=mine, page=page, page_size=page_size)
    return StandardResponse(success=True, message="Generated reports retrieved", data=data)


@router.post("/preview", response_model=StandardResponse)
def preview_report(
    configuration: ReportConfiguration,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportService(db).preview(configuration, _scope(db, request))
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StandardResponse(success=True, message="Report preview generated", data=data)


@router.post("/generate", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def generate_report(
    configuration: ReportConfiguration,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("export_data")),
):
    try:
        service = ReportService(db)
        report = service.generate(configuration, _scope(db, request))
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StandardResponse(
        success=True,
        message="Report generated successfully",
        data=service.serialize_generated(report),
    )


@router.get("/saved-templates", response_model=StandardResponse)
def list_saved_report_templates(
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    data = ReportService(db).list_saved_templates(_scope(db, request))
    return StandardResponse(success=True, message="Saved report templates retrieved", data=data)


@router.post("/saved-templates", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def save_report_template(
    payload: SaveReportTemplateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        service = ReportService(db)
        template = service.save_template(payload.template_name, payload.configuration, _scope(db, request))
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StandardResponse(
        success=True,
        message="Report template saved",
        data={"id": str(template.id), "name": template.name},
    )


@router.get("/{report_id}/download")
def download_report(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        report = ReportService(db).get_download(report_id, _scope(db, request))
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StreamingResponse(
        BytesIO(report.file_data),
        media_type=report.content_type,
        headers={"Content-Disposition": f'attachment; filename="{report.file_name}"'},
    )
