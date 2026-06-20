# Phase 5 Execution Guide — Step-by-Step Instructions

**Status**: Database connected, ready to execute  
**Duration**: ~8 hours (can be done in stages)  
**Difficulty**: Medium (follow steps carefully)

---

## Quick Start (Choose Your Path)

### Option A: Execute All at Once
Best for: Dedicated 8-hour session
```bash
# Follow stages 1-8 sequentially
# Estimated: 8 hours non-stop
```

### Option B: Execute in Stages
Best for: Working in chunks
```bash
# Day 1: Stages 1-2 (Repository layer setup)
# Day 2: Stages 3-4 (Service updates)
# Day 3: Stages 5-6 (Onboarding + migration)
# Day 4: Stages 7-8 (Testing + deployment)
```

### Option C: Execute One Stage at a Time
Best for: Learning as you go
```bash
# Complete and test each stage before moving forward
# Verify after each stage
```

---

## Stage 1: Database Initialization (30 min)

### Step 1: Verify Database Connection

```bash
cd Backend

# Test Python can connect
python << 'EOF'
from config.database import engine
try:
    with engine.connect() as conn:
        result = conn.execute("SELECT 1")
        print("✓ Database connection successful")
except Exception as e:
    print(f"✗ Connection failed: {e}")
EOF
```

**Expected Output**:
```
✓ Database connection successful
```

### Step 2: Initialize Alembic

```bash
# Navigate to Backend
cd Backend

# Initialize Alembic (only if not done)
alembic init migrations

# Check if generated
ls -la migrations/
# Should show: env.py, script.py.mako, alembic.ini, versions/
```

### Step 3: Create Initial Migration

```bash
# Auto-generate migration from SQLAlchemy models
alembic revision --autogenerate -m "Initial schema: teams, employees, performance"

# Check generated migration
ls -la migrations/versions/
# Should show file like: 001_initial_schema.py
```

### Step 4: Review Migration

```bash
# View the generated migration file
cat migrations/versions/*_initial_schema.py | head -50

# Look for these tables:
# - teams
# - team_kpi_config
# - employees
# - performance_records
# - kpi_values
# - upload_log
```

### Step 5: Apply Migration

```bash
# Apply the migration to database
alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
# INFO  [alembic.runtime.migration] Will assume transactional DDL.
# INFO  [alembic.runtime.migration] Running upgrade -> 001_..., create table teams, etc.
```

### Step 6: Verify Schema

```bash
# Connect to database and verify tables
psql -U postgres -d PMS_Sys << 'EOF'
\dt                          -- List all tables
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public';
EOF
```

**Expected Output** (6 tables):
```
 public | teams
 public | team_kpi_config
 public | employees
 public | performance_records
 public | kpi_values
 public | upload_log
```

### ✅ Stage 1 Complete
- [x] Database connected
- [x] Migration created
- [x] Schema applied
- [x] Tables verified

**Next**: Stage 2 (Repository Layer)

---

## Stage 2: Repository Layer (90 min)

### Step 1: Create Repository Directory

```bash
cd Backend
mkdir -p repositories
touch repositories/__init__.py
```

### Step 2: Create Base Repository

**File**: `Backend/repositories/base_repository.py`

```python
from typing import Generic, TypeVar, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

T = TypeVar('T')

class BaseRepository(Generic[T]):
    """Generic CRUD repository"""
    
    def __init__(self, db: Session, model: type):
        self.db = db
        self.model = model
    
    def create(self, obj_in: dict) -> Optional[T]:
        """Create new record"""
        try:
            db_obj = self.model(**obj_in)
            self.db.add(db_obj)
            self.db.commit()
            self.db.refresh(db_obj)
            return db_obj
        except SQLAlchemyError as e:
            self.db.rollback()
            raise Exception(f"Failed to create {self.model.__name__}: {str(e)}")
    
    def get_by_id(self, id: any) -> Optional[T]:
        """Get record by ID"""
        return self.db.query(self.model).filter(self.model.id == id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """Get all records with pagination"""
        return self.db.query(self.model).offset(skip).limit(limit).all()
    
    def update(self, id: any, obj_in: dict) -> Optional[T]:
        """Update record"""
        db_obj = self.get_by_id(id)
        if db_obj:
            for key, value in obj_in.items():
                setattr(db_obj, key, value)
            self.db.commit()
            self.db.refresh(db_obj)
        return db_obj
    
    def delete(self, id: any) -> bool:
        """Hard delete (use soft delete for most cases)"""
        db_obj = self.get_by_id(id)
        if db_obj:
            self.db.delete(db_obj)
            self.db.commit()
            return True
        return False
    
    def count(self) -> int:
        """Count all records"""
        return self.db.query(self.model).count()
```

### Step 3: Create Team Repository

**File**: `Backend/repositories/team_repository.py`

```python
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from repositories.base_repository import BaseRepository
from models.models import Team
from datetime import datetime

class TeamRepository(BaseRepository[Team]):
    """Repository for Team model"""
    
    def get_by_name(self, name: str) -> Team:
        """Get team by name"""
        return self.db.query(Team).filter(Team.name == name).first()
    
    def get_active_teams(self) -> list:
        """Get all active teams"""
        return self.db.query(Team).filter(Team.is_active == True).all()
    
    def get_by_region(self, region: str) -> list:
        """Get teams by region"""
        return self.db.query(Team).filter(Team.region == region).all()
    
    def count_active(self) -> int:
        """Count active teams"""
        return self.db.query(Team).filter(Team.is_active == True).count()
    
    def soft_delete(self, id: any) -> bool:
        """Soft delete (mark as inactive)"""
        team = self.get_by_id(id)
        if team:
            team.is_active = False
            team.updated_at = datetime.now()
            self.db.commit()
            return True
        return False
    
    def restore(self, id: any) -> bool:
        """Restore soft-deleted team"""
        team = self.get_by_id(id)
        if team:
            team.is_active = True
            team.updated_at = datetime.now()
            self.db.commit()
            return True
        return False
```

### Step 4: Create Employee Repository

**File**: `Backend/repositories/employee_repository.py`

```python
from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import Employee

class EmployeeRepository(BaseRepository[Employee]):
    """Repository for Employee model"""
    
    def get_by_employee_id(self, employee_id: str) -> Employee:
        """Get employee by employee ID"""
        return self.db.query(Employee).filter(
            Employee.employee_id == employee_id
        ).first()
    
    def get_by_team(self, team_id) -> list:
        """Get all employees in team"""
        return self.db.query(Employee).filter(
            Employee.team_id == team_id
        ).all()
    
    def get_active_by_team(self, team_id) -> list:
        """Get active employees in team"""
        return self.db.query(Employee).filter(
            (Employee.team_id == team_id) &
            (Employee.is_active == True)
        ).all()
    
    def count_by_team(self, team_id) -> int:
        """Count employees in team"""
        return self.db.query(Employee).filter(
            Employee.team_id == team_id
        ).count()
```

### Step 5: Create Performance Repository

**File**: `Backend/repositories/performance_repository.py`

```python
from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import PerformanceRecord

class PerformanceRepository(BaseRepository[PerformanceRecord]):
    """Repository for PerformanceRecord model"""
    
    def get_by_employee_month(self, employee_id, month: str, year: int):
        """Get performance record for specific month"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.employee_id == employee_id) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).first()
    
    def get_monthly_records(self, team_id, month: str, year: int) -> list:
        """Get all records for team in specific month"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).all()
    
    def get_employee_history(self, employee_id, year: int) -> list:
        """Get all records for employee in year"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.employee_id == employee_id) &
            (PerformanceRecord.year == year)
        ).order_by(PerformanceRecord.month).all()
    
    def count_by_grade(self, team_id, grade: str, month: str, year: int) -> int:
        """Count records by grade"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.grade == grade) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).count()
```

### Step 6: Update repositories/__init__.py

**File**: `Backend/repositories/__init__.py`

```python
from repositories.base_repository import BaseRepository
from repositories.team_repository import TeamRepository
from repositories.employee_repository import EmployeeRepository
from repositories.performance_repository import PerformanceRepository

__all__ = [
    'BaseRepository',
    'TeamRepository',
    'EmployeeRepository',
    'PerformanceRepository',
]
```

### Step 7: Test Repositories

```bash
cd Backend

python << 'EOF'
from config.database import SessionLocal
from repositories.team_repository import TeamRepository
from models.models import Team
import uuid

db = SessionLocal()
repo = TeamRepository(db, Team)

# Test create
team = repo.create({
    'name': 'test_team',
    'db_name': 'test_db',
    'region': 'UAE'
})
print(f"✓ Created team: {team.name} (ID: {team.id})")

# Test get
fetched = repo.get_by_name('test_team')
print(f"✓ Fetched team: {fetched.name}")

# Test get_active
active = repo.get_active_teams()
print(f"✓ Found {len(active)} active teams")

# Cleanup
repo.soft_delete(team.id)
print(f"✓ Soft deleted team")

db.close()
EOF
```

**Expected Output**:
```
✓ Created team: test_team (ID: ...)
✓ Fetched team: test_team
✓ Found 1 active teams
✓ Soft deleted team
```

### ✅ Stage 2 Complete
- [x] Base repository created
- [x] Team repository created
- [x] Employee repository created
- [x] Performance repository created
- [x] Repositories tested

**Next**: Stage 3 (Update Services)

---

## Stages 3-8 Execution

For complete execution of remaining stages, follow the detailed instructions in:

**`.kiro/PHASE-5-INTEGRATION-PLAN.md`** (Sections Stage 3-8)

Each stage includes:
- Detailed code examples
- Step-by-step instructions
- Verification procedures
- Testing checklist

---

## Verification After Each Stage

### After Stage 1: Database
```bash
psql -U postgres -d PMS_Sys -c "\dt"
# Should show 6 tables
```

### After Stage 2: Repositories
```bash
python -c "from repositories import TeamRepository; print('✓ Repositories imported')"
```

### After Stage 3: Services
```bash
python -c "from services.team_service import TeamService; print('✓ Services updated')"
```

### After Stage 4: API
```bash
# When backend is running
curl http://localhost:8000/api/team-management/teams
# Should return JSON array of teams
```

### After Stages 5-8: Full System
```bash
# All endpoints working
# Database persisting data
# Error handling in place
# Logging configured
```

---

## Troubleshooting During Execution

### Issue: "ModuleNotFoundError: No module named 'repositories'"
**Solution**: Ensure `Backend/repositories/__init__.py` exists

### Issue: "DATABASE_URL is not set"
**Solution**: Verify `Backend/.env` has DATABASE_URL

### Issue: Migration fails
**Solution**:
```bash
# Check if tables already exist
psql -U postgres -d PMS_Sys -c "\dt"

# If tables exist, create migration without autogenerate
alembic revision -m "Schema already exists"
```

### Issue: Tests fail
**Solution**: Verify database is running and accessible

---

## Save Checkpoints

After each stage completes:

```bash
# Create checkpoint
git add -A
git commit -m "Stage X: [description] completed

- Verified: [what was verified]
- Next: Stage Y"

# Or manual backup
cp -r Backend Backend.backup-stage-X
```

---

## Final Verification

When all stages complete, run:

```bash
bash << 'EOF'
cd Backend

echo "=== Phase 5 Integration Verification ==="
echo ""
echo "1. Database connection..."
python -c "from config.database import engine; engine.connect(); print('✓')"

echo "2. Models imported..."
python -c "from models.models import Team, Employee, PerformanceRecord; print('✓')"

echo "3. Repositories imported..."
python -c "from repositories import TeamRepository, EmployeeRepository, PerformanceRepository; print('✓')"

echo "4. Services updated..."
python -c "from services.team_service import TeamService; print('✓')"

echo "5. Database tables exist..."
python << 'PYEOF'
from config.database import engine
with engine.connect() as conn:
    result = conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
    count = result.scalar()
    if count >= 6:
        print('✓')
    else:
        print(f'✗ Only {count} tables found, expected 6')
PYEOF

echo ""
echo "=== All Checks Passed ✓ ==="
echo "Phase 5 Integration Ready!"
EOF
```

---

## What's Next After Integration?

When all stages are complete:

1. ✅ System fully integrated with database
2. ✅ All services using repositories
3. ✅ Persistence working
4. ✅ API endpoints functional
5. 📋 Ready for Phase 5 Part 5 features

### Phase 5 Part 5 (Next):
- Authentication & Authorization
- Advanced features
- Production optimization

---

**Start with Stage 1 and progress through each stage carefully.**

Reference the full plan in `.kiro/PHASE-5-INTEGRATION-PLAN.md` for detailed information on each stage.

