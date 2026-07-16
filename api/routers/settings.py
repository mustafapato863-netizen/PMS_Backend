from fastapi import APIRouter, Depends

from api.dependencies import weights_repo, targets_repo, performance_repo, kpi_service
from api.middleware.rbac_middleware import require_permission
from models.schemas import StandardResponse, KPIWeight, Target

router = APIRouter()

@router.get("/weights", response_model=StandardResponse)
async def get_weights():
    try:
        weights = weights_repo.get_all()
        return StandardResponse(success=True, message="KPI Weights retrieved", data=[w.model_dump() for w in weights])
    except Exception as e:
        return StandardResponse(success=False, message="Failed to load KPI weights.")

@router.post("/weights", response_model=StandardResponse)
async def update_weights(
    payload: KPIWeight,
    _user=Depends(require_permission("manage_permissions"))
):
    try:
        weights_repo.save(payload)
        return StandardResponse(success=True, message="KPI Weights updated", data=payload.model_dump())
    except Exception as e:
        return StandardResponse(success=False, message="Failed to save KPI weights.")

@router.get("/targets", response_model=StandardResponse)
async def get_targets():
    try:
        targets = targets_repo.get_all()
        return StandardResponse(success=True, message="KPI Targets retrieved", data=[t.model_dump() for t in targets])
    except Exception as e:
        return StandardResponse(success=False, message="Failed to load targets.")

@router.post("/targets", response_model=StandardResponse)
async def update_targets(
    payload: Target,
    _user=Depends(require_permission("manage_permissions"))
):
    try:
        targets_repo.save(payload)
        
        records = performance_repo.get_all()
        updated_records = []
        for r in records:
            if r.team == payload.team:
                score, grade, achievements, weights_used = kpi_service.calculate_performance(
                    r.team, r.raw_data, r.performance_level
                )
                
                r.achievement.booking_ach = achievements.get("Booking", 0.0)
                r.achievement.attend_ach = achievements.get("Attend", 0.0)
                r.achievement.quality_ach = achievements.get("Quality") or achievements.get("quality_errors_rate") or 0.0
                r.achievement.aht_ach = achievements.get("AHT", 0.0)
                r.achievement.reachability_ach = achievements.get("Other", 0.0) if r.team == "Outbound" else 0.0
                r.achievement.abandon_ach = achievements.get("Other", 0.0) if r.team in ["Inbound", "Inbound UAE"] else 0.0
                r.achievement.rejection_ach = (
                    achievements.get("Rejection")
                    or achievements.get("initial_rejection_rate")
                    or achievements.get("rejection_rate_after_resubmission")
                    or 0.0
                )
                r.achievement.initial_error_ach = achievements.get("InitialError", 0.0)
                r.achievement.submission_ach = (
                    achievements.get("Submission")
                    or achievements.get("submission_within_due_date")
                    or achievements.get("tat")
                    or 0.0
                )
                
                r.actual.booking_rate = float(r.raw_data.get("A.Booking%", 0.0))
                r.actual.attend_rate = float(r.raw_data.get("A.Attend%", 0.0))
                r.actual.abandon_rate = float(r.raw_data.get("A.AbandonRate%", 0.0))
                r.actual.reachability_rate = float(r.raw_data.get("A.Reachability%", 0.0))
                r.actual.rejection_rate = float(
                    r.raw_data.get("A.InitialRejectionRate")
                    or r.raw_data.get("IPInitialRejection%")
                    or r.raw_data.get("A.CSRRejection%")
                    or r.raw_data.get("A.RejectionRateAfterResubmission")
                    or r.raw_data.get("A.RejectionRateAfterRe-Submission")
                    or 0.0
                )
                r.actual.initial_error_rate = float(r.raw_data.get("Error%", 0.0))
                r.actual.submission_rate = float(
                    r.raw_data.get("A.TAT48Hours")
                    or r.raw_data.get("NumberApprovalwithin48hrs")
                    or r.raw_data.get("A.TAT")
                    or 0.0
                )
                r.actual.quality_rate = float(r.raw_data.get("A.QualityScore") or r.raw_data.get("A.QualityErrorsRate") or 0.0)
                r.actual.utz_rate = float(r.raw_data.get("A.UTZ%", 0.0))
                
                r.evaluation.score = score
                r.evaluation.grade = grade
                
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
        return StandardResponse(success=False, message="Failed to save targets.")
