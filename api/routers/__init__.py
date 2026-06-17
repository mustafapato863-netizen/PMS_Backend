from fastapi import APIRouter

from .performance import router as performance_router
from .employee import router as employee_router
from .team import router as team_router
from .settings import router as settings_router
from .upload import router as upload_router
from .users_and_actions import users_router, actions_router

router = APIRouter()

router.include_router(performance_router, tags=["Performance"])
router.include_router(employee_router, prefix="/employee", tags=["Employee"])
router.include_router(team_router, prefix="/team-actions", tags=["Team Actions"])
router.include_router(settings_router, prefix="/settings", tags=["Settings"])
router.include_router(upload_router, prefix="/uploads", tags=["Uploads"])
router.include_router(users_router, prefix="/users", tags=["Users"])
router.include_router(actions_router, prefix="/corrective-actions", tags=["Corrective Actions"])
