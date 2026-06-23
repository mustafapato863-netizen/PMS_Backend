import datetime
from services.socket_service import SocketNotificationService
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Dict, List
from uuid import UUID

from api.dependencies import (
    employee_repo, performance_repo, actions_repo, notes_repo, learning_service,
    serialize_performance_record, require_role, get_current_user_scope, filter_records_by_scope, user_can_access_team
)
from config.database import get_db
from sqlalchemy.orm import Session
from models.schemas import StandardResponse, ManagerNote, CorrectiveAction
from services.employee_service import EmployeeService
from services.performance_service import PerformanceService

router = APIRouter(prefix="", tags=["Employees"])

@router.get("", response_model=StandardResponse)
def get_all_employees(include_deleted: bool = Query(False)):
    """
    Get all employees from database.
    
    Returns:
        List of all employees
    """
    try:
        employees = employee_repo.get_all()
        data = [e.model_dump() for e in employees]
        if not include_deleted:
            data = [e for e in data if e.get("status", "Active") != "Inactive"]
        return StandardResponse(
            success=True,
            message=f"Retrieved {len(data)} employees",
            data=data
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to retrieve employees: {str(e)}"
        )


@router.get("/search", response_model=StandardResponse)
def  search_employees(name: str = Query(...), include_deleted: bool = Query(False)):
    """
    Search employees by name.
    
    Args:
        name: Name to search for
        
    Returns:
        List of matching employees
    """
    try:
        employees = employee_repo.get_all()
        name_lower = name.lower()
        matched = [e for e in employees if name_lower in e.name.lower()]
        data = [e.model_dump() for e in matched]
        if not include_deleted:
            data = [e for e in data if e.get("status", "Active") != "Inactive"]
        return StandardResponse(
            success=True,
            message=f"Found {len(data)} employees matching '{name}'",
            data=data
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to search employees: {str(e)}"
        )


@router.get("/team/{team_name}", response_model=StandardResponse)
def get_employees_by_team(team_name: str, include_deleted: bool = Query(False)):
    """
    Get all employees in a team.
    
    Args:
        team_name: Team name
        
    Returns:
        List of employees in team
    """
    try:
        employees = employee_repo.get_all()
        matched = [e for e in employees if e.team == team_name]
        data = [e.model_dump() for e in matched]
        if not include_deleted:
            data = [e for e in data if e.get("status", "Active") != "Inactive"]
        return StandardResponse(
            success=True,
            message=f"Retrieved {len(data)} employees for team",
            data=data
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to retrieve team employees: {str(e)}"
        )


@router.get("/team/{team_name}/active", response_model=StandardResponse)
def get_active_employees_by_team(team_name: str):
    """
    Get all active employees in a team.
    
    Args:
        team_name: Team name
        
    Returns:
        List of active employees in team
    """
    try:
        employees = employee_repo.get_all()
        matched = [e for e in employees if e.team == team_name and e.status == "Active"]
        data = [e.model_dump() for e in matched]
        return StandardResponse(
            success=True,
            message=f"Retrieved {len(data)} active employees for team",
            data=data
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to retrieve active team employees: {str(e)}"
        )


@router.post("", response_model=StandardResponse, status_code=201)
def  create_employee(
    employee_id: str = Query(...),
    name: str = Query(...),
    team: str = Query(...),
    region: str = Query("UAE"),
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    """
    Create a new employee.
    
    Args:
        employee_id: External employee ID
        name: Employee name
        team: Team name
        region: Region (default: UAE)
        
    Returns:
        Created employee
    """
    try:
        from models.schemas import Employee as EmployeeSchema
        emp = EmployeeSchema(id=employee_id, name=name, team=team, region=region)
        employee_repo.save(emp)
        return StandardResponse(
            success=True,
            message="Employee created successfully",
            data=emp.model_dump()
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to create employee: {str(e)}"
        )


@router.get("/{employee_id}", response_model=StandardResponse)
def get_employee_profile(employee_id: str, request: Request, db: Session = Depends(get_db), include_deleted: bool = Query(False)):
    """
    Get employee profile including performance history.
    
    Args:
        employee_id: Employee ID from Excel
        
    Returns:
        Employee profile with performance history
    """
    try:
        # Look up employee from JSON repo
        employees = employee_repo.get_all()
        emp = next((e for e in employees if str(e.id) == employee_id or e.name == employee_id), None)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        scope = get_current_user_scope(db, request)
        if not scope.get("legacy_unscoped") and scope.get("role") == "Manager" and not scope.get("is_general_manager"):
            if not user_can_access_team(scope, emp.team):
                raise HTTPException(status_code=403, detail="Access denied for this employee")
        elif not scope.get("legacy_unscoped") and scope.get("role") in {"Agent", "Executive"}:
            self_id = str(scope.get("employee_id") or scope.get("user_id") or "")
            if str(emp.id) != self_id:
                raise HTTPException(status_code=403, detail="Access denied for this employee")

        records = performance_repo.get_all()
        records = filter_records_by_scope(records, scope)
        emp_records = [r for r in records if str(r.employee_id) == str(emp.id)]
        
        from services.planning_service import MONTH_ORDER
        emp_records.sort(key=lambda x: MONTH_ORDER.get(x.month, 0))

        history = actions_repo.get_history(emp.id)
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


@router.put("/{employee_id}", response_model=StandardResponse)
def  update_employee(
    employee_id: str,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Query(None),
    team: str = Query(None),
    region: str = Query(None),
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    """
    Update an employee.
    
    Args:
        employee_id: Employee ID
        name: Updated name (optional)
        team: Updated team name (optional)
        region: Updated region (optional)
        
    Returns:
        Updated employee
    """
    try:
        emp = employee_repo.get_by_id(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        scope = get_current_user_scope(db, request)
        if not scope.get("legacy_unscoped") and scope.get("role") == "Manager" and not scope.get("is_general_manager"):
            if not user_can_access_team(scope, emp.team):
                raise HTTPException(status_code=403, detail="Access denied for this employee")
        elif not scope.get("legacy_unscoped") and scope.get("role") in {"Agent", "Executive"}:
            self_id = str(scope.get("employee_id") or scope.get("user_id") or "")
            if str(emp.id) != self_id:
                raise HTTPException(status_code=403, detail="Access denied for this employee")

        data = emp.model_dump()
        if name is not None:
            data['name'] = name
        if team is not None:
            data['team'] = team
        if region is not None:
            data['region'] = region
        
        from models.schemas import Employee as EmployeeSchema
        updated = EmployeeSchema(**data)
        employee_repo.save(updated)
        return StandardResponse(
            success=True,
            message="Employee updated successfully",
            data=updated.model_dump()
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to update employee: {str(e)}"
        )


@router.delete("/{employee_id}", response_model=StandardResponse)
def  delete_employee(
    employee_id: str,
    request: Request,
    role: str = Depends(require_role(["Admin"]))
):
    """
    Delete (deactivate) an employee.
    
    Args:
        employee_id: Employee UUID
        
    Returns:
        Deletion confirmation
    """
    try:
        performed_by_user_id = request.state.user.get("user_id") if hasattr(request.state, "user") and request.state.user else None
        success, errors = EmployeeService.delete_employee(employee_id, performed_by_user_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        
        return StandardResponse(
            success=True,
            message="Employee deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to delete employee: {str(e)}"
        )


@router.post("/{employee_id}/restore", response_model=StandardResponse)
def  restore_employee(
    employee_id: str,
    request: Request,
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    """
    Restore a soft-deleted employee.
    
    Args:
        employee_id: Employee UUID
        
    Returns:
        Restoration confirmation
    """
    try:
        performed_by_user_id = request.state.user.get("user_id") if hasattr(request.state, "user") and request.state.user else None
        success, errors = EmployeeService.restore_employee(employee_id, performed_by_user_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        
        return StandardResponse(
            success=True,
            message="Employee restored successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to restore employee: {str(e)}"
        )


@router.post("/{employee_id}/notes", response_model=StandardResponse)
def  save_notes(
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
async def  save_corrective_action(
    employee_id: str,
    payload: Dict[str, str],
    request: Request,
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

        current_user = getattr(request.state, "user", None) or {}
        created_by_name = current_user.get("name") or current_user.get("username") or current_user.get("role") or "Unknown"
        created_by_role = current_user.get("role") or role

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
                timestamp=datetime.datetime.now().isoformat(),
                created_by_name=created_by_name,
                created_by_role=created_by_role,
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

        await SocketNotificationService.notify_action_assigned(
            employee_name=perf.employee_name,
            action_type=manager_action.split(': ', 1)[0] if ': ' in manager_action else 'Coaching',
            team_name=perf.team,
            created_by_name=created_by_name,
            created_by_role=created_by_role,
            is_update=bool(existing_action),
        )

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

        await SocketNotificationService.notify_info(
            info_message=f"Action deleted for {target_action.employee_name}: {target_action.manager_action}",
            team_name=target_action.team
        )

        return StandardResponse(
            success=True,
            message="Corrective Action deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to delete corrective action: {str(e)}")

@router.get("/{employee_id}/recommendations", response_model=StandardResponse)
def get_action_recommendations(employee_id: str, month: str = Query(...)):
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
