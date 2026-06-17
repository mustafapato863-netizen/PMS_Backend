from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import user_repo, actions_repo, require_role
from models.schemas import StandardResponse, UserRecord, LoginPayload

users_router = APIRouter()

@users_router.get("/", response_model=StandardResponse)
async def get_users(
    role: str = Depends(require_role(["Admin"]))
):
    try:
        users = user_repo.get_all()
        return StandardResponse(
            success=True,
            message="Users retrieved successfully",
            data=[u.model_dump() for u in users]
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to fetch users: {str(e)}")

@users_router.post("/", response_model=StandardResponse)
async def create_user(
    payload: UserRecord,
    role: str = Depends(require_role(["Admin"]))
):
    try:
        user_repo.save(payload)
        return StandardResponse(
            success=True,
            message="User created successfully",
            data=payload.model_dump()
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to create user: {str(e)}")

@users_router.delete("/{user_id}", response_model=StandardResponse)
async def delete_user_route(
    user_id: str,
    role: str = Depends(require_role(["Admin"]))
):
    try:
        success = user_repo.delete(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return StandardResponse(
            success=True,
            message="User deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to delete user: {str(e)}")

@users_router.post("/login", response_model=StandardResponse)
async def login_user(payload: LoginPayload):
    try:
        users = user_repo.get_all()
        found = None
        for u in users:
            if u.username.lower() == payload.username.strip().lower() and u.password == payload.password:
                found = u
                break
        if not found:
            return StandardResponse(success=False, message="Invalid username or password")
        
        user_data = found.model_dump()
        user_data.pop("password", None)
        return StandardResponse(
            success=True,
            message="Login successful",
            data=user_data
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Login failed: {str(e)}")

actions_router = APIRouter()

@actions_router.get("/", response_model=StandardResponse)
async def get_all_corrective_actions(
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        actions = actions_repo.get_history()
        return StandardResponse(
            success=True,
            message="Retrieved all corrective actions successfully",
            data=[a.model_dump() for a in actions]
        )
    except Exception as e:
        return StandardResponse(success=False, message=f"Failed to fetch corrective actions: {str(e)}")
