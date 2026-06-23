"""
Team Management Router
API endpoints for managing teams (CRUD operations).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from models.team_models import (
    TeamResponse,
    TeamListResponse,
    TeamCreateRequest,
    TeamUpdateRequest,
    TeamValidationResponse,
    TeamOnboardingRequest,
    TeamOnboardingResponse,
)
from services.team_service import TeamService
from services.team_onboarding_service import TeamOnboardingService
from api.middleware.rbac_middleware import require_permission

router = APIRouter(prefix="/team-management", tags=["Team Management"])


@router.get("/teams", response_model=TeamListResponse)
async def list_teams():
    """
    List all teams.
    
    Returns:
        List of all team configurations
    """
    teams = TeamService.get_all_teams()
    active_count = sum(1 for t in teams if t.get('is_active', True))
    inactive_count = len(teams) - active_count
    
    return TeamListResponse(
        teams=[TeamResponse(**t) for t in teams],
        total=len(teams),
        active_count=active_count,
        inactive_count=inactive_count,
    )


@router.get("/teams/{team_name}", response_model=TeamResponse)
async def get_team(team_name: str):
    """
    Get team by name.
    
    Args:
        team_name: Team identifier
        
    Returns:
        Team configuration
        
    Raises:
        HTTPException: If team not found
    """
    team = TeamService.get_team(team_name)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{team_name}' not found"
        )
    
    return TeamResponse(**team)


@router.post("/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    request: TeamCreateRequest,
    _user=Depends(require_permission("create_team"))
):
    """
    Create new team.
    
    Args:
        request: Team creation request
        
    Returns:
        Created team configuration
        
    Raises:
        HTTPException: If creation fails
    """
    success, team_config, errors = TeamService.create_team(request)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(errors)
        )
    
    return TeamResponse(**team_config)


@router.put("/teams/{team_name}", response_model=TeamResponse)
async def update_team(
    team_name: str,
    request: TeamUpdateRequest,
    _user=Depends(require_permission("edit_team_config"))
):
    """
    Update team configuration.
    
    Args:
        team_name: Team identifier
        request: Update request
        
    Returns:
        Updated team configuration
        
    Raises:
        HTTPException: If update fails
    """
    success, team_config, errors = TeamService.update_team(team_name, request)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(errors)
        )
    
    return TeamResponse(**team_config)


@router.delete("/teams/{team_name}", status_code=status.HTTP_200_OK)
async def delete_team(
    team_name: str,
    _user=Depends(require_permission("delete_team"))
):
    """
    Delete (deactivate) team.
    
    Args:
        team_name: Team identifier
        
    Returns:
        Deletion confirmation
        
    Raises:
        HTTPException: If deletion fails
    """
    success, errors = TeamService.delete_team(team_name)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(errors)
        )
    
    return {
        "success": True,
        "message": f"Team '{team_name}' deleted successfully",
    }


@router.post("/teams/{team_name}/validate", response_model=TeamValidationResponse)
async def validate_team(team_name: str):
    """
    Validate team configuration.
    
    Args:
        team_name: Team identifier
        
    Returns:
        Validation result with errors and warnings
    """
    is_valid, errors, warnings = TeamService.validate_team(team_name)
    
    if not is_valid and not errors:
        # Team not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{team_name}' not found"
        )
    
    status_message = "Team configuration is valid"
    if errors:
        status_message = f"Validation failed: {len(errors)} error(s)"
    elif warnings:
        status_message = f"Team configuration is valid with {len(warnings)} warning(s)"
    
    return TeamValidationResponse(
        valid=is_valid,
        team_name=team_name,
        errors=errors,
        warnings=warnings,
        message=status_message,
    )


@router.get("/statistics")
async def get_statistics():
    """
    Get team statistics.
    
    Returns:
        Statistics about teams in system
    """
    stats = TeamService.get_team_statistics()
    return {
        "success": True,
        "data": stats,
    }


@router.post("/teams/{team_name}/onboard", response_model=TeamOnboardingResponse)
async def start_onboarding(
    team_name: str,
    request: TeamOnboardingRequest,
    _user=Depends(require_permission("create_team"))
):
    """
    Start team onboarding workflow.
    
    Initiates the automated team setup process including:
    - Team configuration initialization
    - Directory structure creation
    - Initial data seeding
    - Alert configuration
    - Dashboard enablement
    - Completion notification
    
    Args:
        team_name: Team identifier
        request: Onboarding request parameters
        
    Returns:
        Onboarding status and step details
        
    Raises:
        HTTPException: If team not found or onboarding fails
    """
    # Verify team exists
    team = TeamService.get_team(team_name)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{team_name}' not found"
        )
    
    try:
        # Start onboarding workflow
        response = await TeamOnboardingService.start_onboarding(
            team_name=team_name,
            auto_proceed=request.auto_proceed,
        )
        
        return response
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Onboarding failed: {str(e)}"
        )


@router.get("/teams/{team_name}/onboarding-status", response_model=TeamOnboardingResponse)
async def get_onboarding_status(team_name: str):
    """
    Get current onboarding status for a team.
    
    Args:
        team_name: Team identifier
        
    Returns:
        Current onboarding status and step details
        
    Raises:
        HTTPException: If team not found
    """
    # Verify team exists
    team = TeamService.get_team(team_name)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{team_name}' not found"
        )
    
    try:
        # Get current onboarding status (non-executing check)
        response = await TeamOnboardingService.start_onboarding(
            team_name=team_name,
            auto_proceed=False,
        )
        
        return response
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get onboarding status: {str(e)}"
        )
