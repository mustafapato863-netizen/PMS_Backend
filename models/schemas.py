from pydantic import BaseModel, Field
from typing import Any, Optional, Dict, List

class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Any = None

class Employee(BaseModel):
    id: str
    name: str
    team: str
    status: str = "Active"
    hiring_date: Optional[str] = None

class GeoBreakdown(BaseModel):
    dubai: int = 0
    sharjah: int = 0
    ajman: int = 0
    clinics: int = 0

class GeoData(BaseModel):
    bookings: GeoBreakdown = Field(default_factory=GeoBreakdown)
    attended: GeoBreakdown = Field(default_factory=GeoBreakdown)

class CallsData(BaseModel):
    inbound: int = 0
    outbound: int = 0
    total_handled: int = 0
    abandoned: int = 0
    aht_raw: str = "00:00:00"

class ActualMetrics(BaseModel):
    booking_rate: float = 0.0
    attend_rate: float = 0.0
    abandon_rate: float = 0.0
    reachability_rate: float = 0.0
    rejection_rate: float = 0.0
    initial_error_rate: float = 0.0
    submission_rate: float = 0.0
    quality_rate: float = 0.0
    utz_rate: float = 0.0

class AchievementMetrics(BaseModel):
    booking_ach: float = 0.0
    attend_ach: float = 0.0
    quality_ach: float = 0.0
    aht_ach: float = 0.0
    reachability_ach: float = 0.0
    abandon_ach: float = 0.0
    rejection_ach: float = 0.0
    initial_error_ach: float = 0.0
    submission_ach: float = 0.0

class RootCauseInfo(BaseModel):
    kpi: str
    impact_pct: float
    actual: float
    target: float

class EvaluationData(BaseModel):
    score: float  # Normalized 0-100
    grade: str
    root_cause: Optional[RootCauseInfo] = None
    suggested_action: Optional[str] = None
    corrective_action: Optional[str] = None
    manager_notes: Optional[str] = None
    planning_category: Optional[List[str]] = Field(default_factory=list)
    trend_status: Optional[Dict[str, Any]] = Field(default_factory=dict)

class PerformanceRecord(BaseModel):
    id: str  # Unique composite key: employee_id + "_" + month
    employee_id: str
    employee_name: str
    team: str
    month: str
    calls: CallsData = Field(default_factory=CallsData)
    geo: GeoData = Field(default_factory=GeoData)
    actual: ActualMetrics = Field(default_factory=ActualMetrics)
    achievement: AchievementMetrics = Field(default_factory=AchievementMetrics)
    evaluation: EvaluationData
    upload_id: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)

class KPIWeight(BaseModel):
    team: str
    weights: Dict[str, float]

class Target(BaseModel):
    team: str
    targets: Dict[str, float]

class UploadRecord(BaseModel):
    id: str
    filename: str
    uploaded_at: str
    uploaded_by: str

class ManagerNote(BaseModel):
    employee_id: str
    month: str
    notes: str
    updated_at: str

class CorrectiveAction(BaseModel):
    id: Optional[str] = None
    employee_id: str
    employee_name: str
    team: str
    month: str
    score: float
    grade: str
    root_cause: str
    suggested_action: str
    manager_action: str
    manager_notes: str
    timestamp: str

class PlanningCategoryRecord(BaseModel):
    employee_id: str
    month: str
    category: str

class TeamAction(BaseModel):
    id: Optional[str] = None  # composite key: team_id + "_" + month
    team_id: str
    month: str
    overall_action: str
    updated_at: str
    updated_by: str = "Admin"

class UserRecord(BaseModel):
    id: str
    name: str
    username: str
    password: str
    role: str

class LoginPayload(BaseModel):
    username: str
    password: str
