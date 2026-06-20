# Phase 5 - Stage 4: Update API Routers for Database Integration

**Status**: In Progress  
**Duration**: 60 minutes  
**Objective**: Ensure all API routers work with database-backed services

---

## Overview

### What was done before this stage:
- ✅ Database schema created
- ✅ Alembic migrations configured
- ✅ 6 repositories created with database access
- ✅ Services updated to use repositories
- ✅ Database connection verified

### What this stage does:
- Update API routers to use database-backed services
- Verify response schemas match database models
- Ensure error handling works with database
- Add proper dependency injection
- Test all endpoints

---

## Stage 4 Breakdown

### 4.1 Team Management Router

**File**: `Backend/api/routers/team_management.py`

**Current State**:
- ✅ Already compatible with database-backed services
- Uses `TeamService` which has been updated to use database
- Response models already defined
- Error handling in place

**Required Updates**: NONE - Router is already compatible!

**Why it works**:
```python
# The router calls TeamService methods
teams = TeamService.get_all_teams()  # Now returns from DB via TeamRepository
# Response is converted to Pydantic schema by FastAPI automatically
```

**Verification**:
```bash
GET /api/team-management/teams → Returns list from database
POST /api/team-management/teams → Creates in database
GET /api/team-management/teams/{name} → Queries database
PUT /api/team-management/teams/{name} → Updates database
DELETE /api/team-management/teams/{name} → Soft-deletes from database
```

### 4.2 Employee Router

**File**: `Backend/api/routers/employee.py`

**Current Issues**:
- Uses JSONEmployeeRepository (file-based)
- No database connection
- Not using EmployeeRepository

**Required Updates**:
1. Update dependencies to use database repositories
2. Update endpoints to query database
3. Verify schemas match database models
4. Add proper error handling

**Plan**:
```python
# OLD (JSON-based)
employee_repo = JSONEmployeeRepository()

# NEW (Database-based)
employee_repo = EmployeeRepository(SessionLocal(), Employee)
```

**Changes Required**:
- GET /{employee_id} - Query from database
- POST /{employee_id}/notes - Save to database
- POST /{employee_id}/corrective-actions - Save to database
- GET /{employee_id}/recommendations - Query from database

### 4.3 Performance Router

**File**: `Backend/api/routers/performance.py`

**Current Issues**:
- Uses JSONPerformanceRepository (file-based)
- Not using database PerformanceRepository
- Filtering logic can be improved with database queries

**Required Updates**:
1. Update to use database repositories
2. Use database filtering instead of in-memory
3. Verify response formats

**Changes Required**:
- GET /performance - Query from database with filters
- GET /planning - Use database queries
- GET /insights - Database aggregations
- GET /reports/export - Export from database

---

## Implementation Steps

### Step 1: Update dependencies.py

**Current**:
```python
from repositories.json_repos import JSONEmployeeRepository, JSONPerformanceRepository, ...

employee_repo = JSONEmployeeRepository()
performance_repo = JSONPerformanceRepository()
```

**New**:
```python
from config.database import SessionLocal
from repositories.employee_repository import EmployeeRepository
from repositories.performance_repository import PerformanceRepository
from models.models import Employee, PerformanceRecord

# Create database session
db = SessionLocal()

# Initialize database repositories
employee_repo = EmployeeRepository(db, Employee)
performance_repo = PerformanceRepository(db, PerformanceRecord)
```

### Step 2: Update Employee Router

Update endpoints to work with database:
- Add proper error handling for database errors
- Ensure all queries go to database
- Verify response serialization

### Step 3: Update Performance Router

Update endpoints to:
- Query from database instead of in-memory
- Use database filters for better performance
- Add pagination support

### Step 4: Update Team Management Router

- ✅ No changes needed (already working)
- Verify all endpoints function correctly

---

## Response Schemas

### Team Response Schema
```python
class TeamResponse(BaseModel):
    id: UUID
    name: str
    db_name: str
    region: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
class TeamListResponse(BaseModel):
    teams: List[TeamResponse]
    total: int
    active_count: int
    inactive_count: int
```

### Employee Response Schema
```python
class EmployeeResponse(BaseModel):
    id: UUID
    employee_id: str
    name: str
    team_id: UUID
    is_active: bool
    created_at: datetime
```

### Performance Response Schema
```python
class PerformanceRecordResponse(BaseModel):
    id: UUID
    employee_id: UUID
    month: str
    year: int
    score: Decimal
    grade: str
    status: str
    uploaded_at: datetime
```

---

## Error Handling

### Database Errors
```python
try:
    team = team_repo.get_by_name(name)
except SQLAlchemyError as e:
    raise HTTPException(
        status_code=500,
        detail="Database error: Unable to fetch team"
    )
except Exception as e:
    raise HTTPException(
        status_code=500,
        detail="Internal server error"
    )
```

### Missing Records
```python
if not team:
    raise HTTPException(
        status_code=404,
        detail="Team not found"
    )
```

### Validation Errors
```python
if not request.name:
    raise HTTPException(
        status_code=400,
        detail="Team name is required"
    )
```

---

## Verification Checklist

### Team Management Router
- [ ] GET /api/team-management/teams → Works
- [ ] POST /api/team-management/teams → Works
- [ ] GET /api/team-management/teams/{name} → Works
- [ ] PUT /api/team-management/teams/{name} → Works
- [ ] DELETE /api/team-management/teams/{name} → Works
- [ ] GET /api/team-management/statistics → Works
- [ ] POST /api/team-management/teams/{name}/onboard → Works

### Employee Router
- [ ] GET /api/employees/{employee_id} → Queries database
- [ ] POST /api/employees/{employee_id}/notes → Saves to database
- [ ] POST /api/employees/{employee_id}/corrective-actions → Saves to database
- [ ] DELETE /api/employees/{employee_id}/corrective-actions/{action_id} → Deletes from database
- [ ] GET /api/employees/{employee_id}/recommendations → Works

### Performance Router
- [ ] GET /api/performance → Queries database
- [ ] GET /api/planning → Works with database
- [ ] GET /api/insights → Works with database
- [ ] GET /api/reports/export → Exports from database

### Response Validation
- [ ] All responses use correct schemas
- [ ] Timestamps are ISO format
- [ ] IDs are properly formatted
- [ ] Null values handled correctly

### Error Handling
- [ ] 404 for missing records
- [ ] 400 for invalid input
- [ ] 500 for database errors
- [ ] Error messages are descriptive

---

## Testing Commands

### Test Team Management
```bash
# List teams
curl http://localhost:8000/api/team-management/teams

# Get specific team
curl http://localhost:8000/api/team-management/teams/inbound

# Create team
curl -X POST http://localhost:8000/api/team-management/teams \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test_team",
    "display_name": "Test Team",
    "db_name": "test_db",
    "region": "UAE"
  }'

# Update team
curl -X PUT http://localhost:8000/api/team-management/teams/test_team \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Updated Test Team"}'

# Delete team
curl -X DELETE http://localhost:8000/api/team-management/teams/test_team
```

### Test Employee Endpoints
```bash
# Get employee profile
curl http://localhost:8000/api/employees/{employee_id}

# Save notes
curl -X POST http://localhost:8000/api/employees/{employee_id}/notes \
  -H "Content-Type: application/json" \
  -d '{
    "month": "January",
    "notes": "Good performance"
  }'

# Save corrective action
curl -X POST http://localhost:8000/api/employees/{employee_id}/corrective-actions \
  -H "Content-Type: application/json" \
  -d '{
    "month": "January",
    "manager_action": "Training",
    "manager_notes": "Recommend training"
  }'
```

### Test Performance Endpoints
```bash
# Get performance records
curl http://localhost:8000/api/performance

# Get performance for specific month
curl "http://localhost:8000/api/performance?month=January"

# Get performance for specific team
curl "http://localhost:8000/api/performance?team=inbound"

# Get planning categories
curl "http://localhost:8000/api/planning?month=January"

# Export report
curl "http://localhost:8000/api/reports/export?month=January&format=excel" \
  -o report.xlsx
```

---

## Success Criteria

- ✅ All routers call database-backed services
- ✅ Response schemas match database models
- ✅ Error handling works correctly
- ✅ All endpoints return 200 for valid requests
- ✅ All endpoints return appropriate error codes (400, 404, 500)
- ✅ No JSON file access in routers
- ✅ All tests passing

---

## Next Steps

After Stage 4 is complete:
1. Move to Stage 5: Team Onboarding Persistence
2. Then Stage 6: Data Migration
3. Then Stage 7: Testing & Verification

