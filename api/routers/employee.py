import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Dict

from api.dependencies import (
    employee_repo, performance_repo, actions_repo, notes_repo, learning_service,
    serialize_performance_record, require_role
)
from models.schemas import StandardResponse, ManagerNote, CorrectiveAction

router = APIRouter()

@router.get("/{employee_id}", response_model=StandardResponse)
async def get_employee_profile(employee_id: str):
    try:
        emp = employee_repo.get_by_id(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        records = performance_repo.get_all()
        emp_records = [r for r in records if r.employee_id == employee_id]
        
        from services.planning_service import MONTH_ORDER
        emp_records.sort(key=lambda x: MONTH_ORDER.get(x.month, 0))

        history = actions_repo.get_history(employee_id)
        history.sort(key=lambda x: x.timestamp, reverse=True)

        profile_data = {
            "employee": emp.model_dump(),
            "performance_history": [serialize_performance_record(r) for r in emp_records],
            "corrective_action_history": [h.model_dump() for h in history]
        }

        return StandardResponse(
            success=True,
            message="Employee profile retrieved successfully",
            data=profile_data
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to retrieve employee profile: {str(e)}")

@router.post("/{employee_id}/notes", response_model=StandardResponse)
async def save_notes(
    employee_id: str,
    payload: Dict[str, str],
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        month = payload.get("month", "")
        notes_text = payload.get("notes", "")
        if not month:
            raise HTTPException(status_code=400, detail="Month is required")

        note = ManagerNote(
            employee_id=employee_id,
            month=month,
            notes=notes_text,
            updated_at=datetime.datetime.now().isoformat()
        )
        notes_repo.save(note)

        perf = performance_repo.get_by_employee_and_month(employee_id, month)
        if perf:
            perf.evaluation.manager_notes = notes_text
            performance_repo.save(perf)

        return StandardResponse(
            success=True,
            message="Manager notes saved successfully",
            data=note.model_dump()
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to save manager notes: {str(e)}")

@router.post("/{employee_id}/corrective-actions", response_model=StandardResponse)
async def save_corrective_action(
    employee_id: str,
    payload: Dict[str, str],
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        month = payload.get("month", "")
        manager_action = payload.get("manager_action", "")
        manager_notes = payload.get("manager_notes", "")
        action_id = payload.get("id")

        if not month or not manager_action:
            raise HTTPException(status_code=400, detail="Month and Corrective Action are required")

        perf = performance_repo.get_by_employee_and_month(employee_id, month)
        if not perf:
            raise HTTPException(status_code=404, detail="Performance record not found for the selected month")

        existing_action = None
        if action_id:
            history = actions_repo.get_history(employee_id)
            for a in history:
                if a.id == action_id:
                    existing_action = a
                    break

        if existing_action:
            existing_action.manager_action = manager_action
            existing_action.manager_notes = manager_notes
            existing_action.timestamp = datetime.datetime.now().isoformat()
            actions_repo.save(existing_action)
            action = existing_action
        else:
            if not action_id:
                action_id = f"{employee_id}_{month}_{datetime.datetime.now().isoformat()}"

            action = CorrectiveAction(
                id=action_id,
                employee_id=employee_id,
                employee_name=perf.employee_name,
                team=perf.team,
                month=month,
                score=perf.evaluation.score,
                grade=perf.evaluation.grade,
                root_cause=perf.evaluation.root_cause.kpi if perf.evaluation.root_cause else "None",
                suggested_action=perf.evaluation.suggested_action or "None",
                manager_action=manager_action,
                manager_notes=manager_notes,
                timestamp=datetime.datetime.now().isoformat()
            )
            actions_repo.save(action)

        remaining = actions_repo.get_history(employee_id)
        latest_for_month = None
        for r in sorted(remaining, key=lambda x: x.timestamp):
            if r.month == month:
                latest_for_month = r

        perf.evaluation.corrective_action = latest_for_month.manager_action if latest_for_month else None
        perf.evaluation.manager_notes = latest_for_month.manager_notes if latest_for_month else None
        performance_repo.save(perf)

        return StandardResponse(
            success=True,
            message="Corrective Action saved successfully",
            data=action.model_dump()
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to save corrective action: {str(e)}")

@router.delete("/{employee_id}/corrective-actions/{action_id}", response_model=StandardResponse)
async def delete_corrective_action(
    employee_id: str,
    action_id: str,
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        history = actions_repo.get_history(employee_id)
        target_action = None
        for a in history:
            if a.id == action_id:
                target_action = a
                break

        if not target_action:
            raise HTTPException(status_code=404, detail="Corrective Action not found")

        month = target_action.month
        actions_repo.delete(action_id)

        remaining = actions_repo.get_history(employee_id)
        latest_for_month = None
        for r in sorted(remaining, key=lambda x: x.timestamp):
            if r.month == month:
                latest_for_month = r

        perf = performance_repo.get_by_employee_and_month(employee_id, month)
        if perf:
            perf.evaluation.corrective_action = latest_for_month.manager_action if latest_for_month else None
            perf.evaluation.manager_notes = latest_for_month.manager_notes if latest_for_month else None
            performance_repo.save(perf)

        return StandardResponse(
            success=True,
            message="Corrective Action deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to delete corrective action: {str(e)}")

@router.get("/{employee_id}/recommendations", response_model=StandardResponse)
async def get_action_recommendations(employee_id: str, month: str = Query(...)):
    try:
        perf = performance_repo.get_by_employee_and_month(employee_id, month)
        if not perf:
            raise HTTPException(status_code=404, detail="Performance record not found")

        root_kpi = perf.evaluation.root_cause.kpi if perf.evaluation.root_cause else "None"
        default_suggest = perf.evaluation.suggested_action or "Performance Monitoring"

        recommendation, preferences = learning_service.get_historical_recommendations(
            team=perf.team,
            score=perf.evaluation.score,
            grade=perf.evaluation.grade,
            root_cause=root_kpi,
            default_suggestion=default_suggest
        )

        return StandardResponse(
            success=True,
            message="Recommendation calculated successfully",
            data={
                "recommendation": recommendation,
                "preferences": preferences
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to calculate recommendations: {str(e)}")
