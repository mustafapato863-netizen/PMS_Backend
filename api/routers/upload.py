from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import datetime

from api.dependencies import uploads_repo, performance_repo, trend_service, planning_service, require_role
from services.seeding_service import DatabaseSeeder
from models.schemas import StandardResponse

router = APIRouter()

@router.get("/", response_model=StandardResponse)
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

@router.post("/pms", response_model=StandardResponse)
async def upload_pms_file(
    file: UploadFile = File(...),
    role: str = Depends(require_role(["Admin"]))
):
    try:
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="Only excel files accepted.")

        contents = await file.read()
        seeder = DatabaseSeeder()
        result = seeder.process_uploaded_file(file.filename, contents)

        return StandardResponse(
            success=True,
            message="PMS Excel uploaded and processed successfully",
            data=result
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return StandardResponse(success=False, message=f"Failed to upload and process Excel file: {str(e)}")

@router.delete("/{upload_id}", response_model=StandardResponse)
async def delete_upload(
    upload_id: str,
    role: str = Depends(require_role(["Admin"]))
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
