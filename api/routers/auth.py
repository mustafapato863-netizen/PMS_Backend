"""Authentication Router
Provides login and logout endpoints.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from config.database import get_db
from models.schemas import LoginPayload, JWTToken, StandardResponse
from services.auth_service import AuthenticationService, redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=StandardResponse)
async def login(payload: LoginPayload, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT token.
    """
    try:
        token = AuthenticationService.authenticate_user(db, payload.username, payload.password)
        
        # Get user details for JWTToken schema
        from models.models import User
        user = db.query(User).filter(User.username == payload.username).first()
        
        token_data = JWTToken(
            access_token=token,
            token_type="bearer",
            role=user.role,
            username=user.username
        )
        
        return StandardResponse(
            success=True,
            message="Successfully authenticated",
            data=token_data.model_dump()
        )
    except ValueError as e:
        # Check if error message indicates lockout
        if "lock" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during authentication."
        )


@router.post("/logout", response_model=StandardResponse)
async def logout(request: Request):
    """
    Log out the current user and invalidate the session cache.
    """
    try:
        # Check if token exists in request state
        if hasattr(request.state, "user"):
            user_id = request.state.user.get("user_id")
            if redis_client:
                try:
                    redis_client.delete(f"session:{user_id}")
                except Exception as ex:
                    logger.warning(f"Failed to clear session in Redis: {ex}")
        
        return StandardResponse(
            success=True,
            message="Successfully logged out"
        )
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during logout."
        )
