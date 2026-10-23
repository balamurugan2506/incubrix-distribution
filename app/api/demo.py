"""Demo Failure-Switch and Management API under /api/v1/demo."""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status
from app.logging_conf import logger

router = APIRouter(prefix="/api/v1/demo", tags=["Live Demo Simulation"])

# In-memory store for demo failure switches
_active_switches: Dict[str, bool] = {
    "timeout": False,
    "rate_limit": False,
    "auth_error": False,
    "schema_mismatch": False
}


class FailureSwitchRequest(BaseModel):
    switch: str = Field(..., description="Failure switch name (timeout, rate_limit, auth_error, schema_mismatch, reset)")
    enabled: bool = Field(True, description="Enable or disable the failure switch")


class FailureSwitchResponse(BaseModel):
    active_switches: Dict[str, bool]
    message: str


@router.get("/failure-switch", response_model=FailureSwitchResponse)
async def get_failure_switches():
    """Retrieve current state of all simulation failure switches."""
    return FailureSwitchResponse(
        active_switches=_active_switches.copy(),
        message="Active failure switch state retrieved successfully."
    )


@router.post("/failure-switch", response_model=FailureSwitchResponse)
async def set_failure_switch(request: FailureSwitchRequest):
    """
    Toggle failure switches to demonstrate resilience during live evaluator tests:
    - timeout: causes external platform calls to simulate timeout-after-create
    - rate_limit: simulates HTTP 429 Rate Limiting
    - auth_error: simulates HTTP 401 expired authentication
    - reset: turns off all failure switches
    """
    if request.switch == "reset":
        for k in _active_switches:
            _active_switches[k] = False
        return FailureSwitchResponse(
            active_switches=_active_switches.copy(),
            message="All demo failure switches have been reset to normal operation."
        )

    if request.switch not in _active_switches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown failure switch '{request.switch}'. Supported switches: {list(_active_switches.keys()) + ['reset']}"
        )

    _active_switches[request.switch] = request.enabled
    logger.info(f"Demo failure switch updated: {request.switch} = {request.enabled}")

    return FailureSwitchResponse(
        active_switches=_active_switches.copy(),
        message=f"Failure switch '{request.switch}' set to {request.enabled}."
    )


def is_switch_active(switch_name: str) -> bool:
    """Helper for middleware and connectors to inspect failure switch state."""
    return _active_switches.get(switch_name, False)
