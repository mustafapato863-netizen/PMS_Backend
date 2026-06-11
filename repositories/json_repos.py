import os
import json
from typing import List, Optional
from config.settings import DATA_DIR
from models.schemas import (
    Employee, PerformanceRecord, KPIWeight, Target, UploadRecord, ManagerNote, CorrectiveAction, TeamAction, UserRecord
)
from repositories.base import (
    EmployeeRepository, PerformanceRepository, KPIWeightsRepository, TargetsRepository,
    UploadsRepository, ManagerNotesRepository, CorrectiveActionsRepository
)

def _load_json(filename: str, default_val: list | dict) -> list | dict:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(default_val, f, indent=2)
        return default_val
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default_val

def _save_json(filename: str, data: list | dict):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class JSONEmployeeRepository(EmployeeRepository):
    def __init__(self):
        self.filename = "employees.json"

    def get_by_id(self, employee_id: str) -> Optional[Employee]:
        data = _load_json(self.filename, [])
        for item in data:
            if str(item.get("id")) == str(employee_id):
                return Employee(**item)
        return None

    def get_all(self) -> List[Employee]:
        data = _load_json(self.filename, [])
        return [Employee(**item) for item in data]

    def save(self, employee: Employee) -> Employee:
        data = _load_json(self.filename, [])
        # Remove existing if exists
        data = [item for item in data if str(item.get("id")) != str(employee.id)]
        data.append(employee.model_dump())
        _save_json(self.filename, data)
        return employee

    def save_all(self, employees: List[Employee]) -> List[Employee]:
        data = _load_json(self.filename, [])
        ids_to_save = {str(e.id) for e in employees}
        data = [item for item in data if str(item.get("id")) not in ids_to_save]
        for e in employees:
            data.append(e.model_dump())
        _save_json(self.filename, data)
        return employees


class JSONPerformanceRepository(PerformanceRepository):
    def __init__(self):
        self.filename = "performance_records.json"

    def get_by_id(self, record_id: str) -> Optional[PerformanceRecord]:
        data = _load_json(self.filename, [])
        for item in data:
            if item.get("id") == record_id:
                return PerformanceRecord(**item)
        return None

    def get_by_employee_and_month(self, employee_id: str, month: str) -> Optional[PerformanceRecord]:
        data = _load_json(self.filename, [])
        for item in data:
            if str(item.get("employee_id")) == str(employee_id) and item.get("month") == month:
                return PerformanceRecord(**item)
        return None

    def get_all(self) -> List[PerformanceRecord]:
        data = _load_json(self.filename, [])
        return [PerformanceRecord(**item) for item in data]

    def save(self, record: PerformanceRecord) -> PerformanceRecord:
        data = _load_json(self.filename, [])
        data = [item for item in data if item.get("id") != record.id]
        data.append(record.model_dump())
        _save_json(self.filename, data)
        return record

    def save_all(self, records: List[PerformanceRecord]) -> List[PerformanceRecord]:
        data = _load_json(self.filename, [])
        ids_to_save = {r.id for r in records}
        data = [item for item in data if item.get("id") not in ids_to_save]
        for r in records:
            data.append(r.model_dump())
        _save_json(self.filename, data)
        return records

    def delete_by_upload_id(self, upload_id: str) -> List[str]:
        data = _load_json(self.filename, [])
        affected_employee_ids = []
        new_data = []
        for item in data:
            if item.get("upload_id") == upload_id:
                emp_id = item.get("employee_id")
                if emp_id:
                    affected_employee_ids.append(str(emp_id))
            else:
                new_data.append(item)
        _save_json(self.filename, new_data)
        return list(set(affected_employee_ids))


class JSONKPIWeightsRepository(KPIWeightsRepository):
    def __init__(self):
        self.filename = "kpi_weights.json"

    def get_by_team(self, team: str) -> Optional[KPIWeight]:
        data = _load_json(self.filename, [])
        for item in data:
            if item.get("team") == team:
                return KPIWeight(**item)
        return None

    def get_all(self) -> List[KPIWeight]:
        data = _load_json(self.filename, [])
        return [KPIWeight(**item) for item in data]

    def save(self, weight: KPIWeight) -> KPIWeight:
        data = _load_json(self.filename, [])
        data = [item for item in data if item.get("team") != weight.team]
        data.append(weight.model_dump())
        _save_json(self.filename, data)
        return weight


class JSONTargetsRepository(TargetsRepository):
    def __init__(self):
        self.filename = "targets.json"

    def get_by_team(self, team: str) -> Optional[Target]:
        data = _load_json(self.filename, [])
        for item in data:
            if item.get("team") == team:
                return Target(**item)
        return None

    def get_all(self) -> List[Target]:
        data = _load_json(self.filename, [])
        return [Target(**item) for item in data]

    def save(self, target: Target) -> Target:
        data = _load_json(self.filename, [])
        data = [item for item in data if item.get("team") != target.team]
        data.append(target.model_dump())
        _save_json(self.filename, data)
        return target


class JSONUploadsRepository(UploadsRepository):
    def __init__(self):
        self.filename = "uploads.json"

    def get_all(self) -> List[UploadRecord]:
        data = _load_json(self.filename, [])
        return [UploadRecord(**item) for item in data]

    def save(self, upload: UploadRecord) -> UploadRecord:
        data = _load_json(self.filename, [])
        data.append(upload.model_dump())
        _save_json(self.filename, data)
        return upload

    def delete_all(self) -> None:
        _save_json(self.filename, [])

    def delete_by_id(self, upload_id: str) -> bool:
        data = _load_json(self.filename, [])
        initial_len = len(data)
        data = [item for item in data if item.get("id") != upload_id]
        _save_json(self.filename, data)
        return len(data) < initial_len


class JSONManagerNotesRepository(ManagerNotesRepository):
    def __init__(self):
        self.filename = "manager_notes.json"

    def get_note(self, employee_id: str, month: str) -> Optional[ManagerNote]:
        data = _load_json(self.filename, [])
        for item in data:
            if str(item.get("employee_id")) == str(employee_id) and item.get("month") == month:
                return ManagerNote(**item)
        return None

    def get_all_notes(self) -> List[ManagerNote]:
        data = _load_json(self.filename, [])
        return [ManagerNote(**item) for item in data]

    def save(self, note: ManagerNote) -> ManagerNote:
        data = _load_json(self.filename, [])
        data = [item for item in data if not (str(item.get("employee_id")) == str(note.employee_id) and item.get("month") == note.month)]
        data.append(note.model_dump())
        _save_json(self.filename, data)
        return note


class JSONCorrectiveActionsRepository(CorrectiveActionsRepository):
    def __init__(self):
        self.filename = "corrective_actions.json"

    def get_latest_by_employee_and_month(self, employee_id: str, month: str) -> Optional[CorrectiveAction]:
        history = self.get_history(employee_id)
        latest = None
        for action in history:
            if action.month == month:
                latest = action
        return latest

    def get_history(self, employee_id: Optional[str] = None) -> List[CorrectiveAction]:
        data = _load_json(self.filename, [])
        actions = []
        updated_any = False
        for item in data:
            if not item.get("id"):
                ts = item.get("timestamp", "default")
                item["id"] = f"{item.get('employee_id')}_{item.get('month')}_{ts}"
                updated_any = True
            actions.append(CorrectiveAction(**item))
        
        if updated_any:
            _save_json(self.filename, data)

        if employee_id:
            actions = [a for a in actions if str(a.employee_id) == str(employee_id)]
        return actions

    def save(self, action: CorrectiveAction) -> CorrectiveAction:
        data = _load_json(self.filename, [])
        if not action.id:
            ts = action.timestamp or "default"
            action.id = f"{action.employee_id}_{action.month}_{ts}"
            
        found = False
        for i, item in enumerate(data):
            curr_id = item.get("id")
            if not curr_id:
                ts = item.get("timestamp", "default")
                curr_id = f"{item.get('employee_id')}_{item.get('month')}_{ts}"
            if curr_id == action.id:
                data[i] = action.model_dump()
                found = True
                break
        if not found:
            data.append(action.model_dump())
            
        _save_json(self.filename, data)
        return action

    def delete(self, action_id: str) -> bool:
        data = _load_json(self.filename, [])
        initial_len = len(data)
        new_data = []
        for item in data:
            curr_id = item.get("id")
            if not curr_id:
                ts = item.get("timestamp", "default")
                curr_id = f"{item.get('employee_id')}_{item.get('month')}_{ts}"
            if curr_id != action_id:
                new_data.append(item)
        _save_json(self.filename, new_data)
        return len(new_data) < initial_len


class JSONTeamActionsRepository:
    def __init__(self):
        self.filename = "team_actions.json"

    def get_action(self, team_id: str, month: str) -> Optional[TeamAction]:
        data = _load_json(self.filename, [])
        for item in data:
            if item.get("team_id") == team_id and item.get("month") == month:
                return TeamAction(**item)
        return None

    def save(self, action: TeamAction) -> TeamAction:
        data = _load_json(self.filename, [])
        action.id = f"{action.team_id}_{action.month}"
        data = [item for item in data if item.get("id") != action.id]
        data.append(action.model_dump())
        _save_json(self.filename, data)
        return action

class JSONUserRepository:
    def __init__(self):
        self.filename = "users.json"
        # Seed default admin user if file is empty/missing
        data = _load_json(self.filename, [])
        if not data:
            default_admin = {
                "id": "admin-1",
                "name": "Admin User",
                "username": "admin",
                "password": "admin123",
                "role": "Admin"
            }
            data.append(default_admin)
            _save_json(self.filename, data)

    def get_all(self) -> List[UserRecord]:
        data = _load_json(self.filename, [])
        return [UserRecord(**item) for item in data]

    def save(self, user: UserRecord) -> UserRecord:
        data = _load_json(self.filename, [])
        # Remove existing if exists
        data = [item for item in data if item.get("id") != user.id and item.get("username").lower() != user.username.lower()]
        data.append(user.model_dump())
        _save_json(self.filename, data)
        return user

    def delete(self, user_id: str) -> bool:
        data = _load_json(self.filename, [])
        initial_len = len(data)
        data = [item for item in data if item.get("id") != user_id]
        _save_json(self.filename, data)
        return len(data) < initial_len
