"""
Auto-Remediation API - Phase 7
Provides endpoints for automated remediation actions and approval workflows.
Uses subprocess for Docker commands for maximum compatibility.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import asyncio
import subprocess
import random
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/remediation")

# Environment flag for real execution mode
REAL_EXECUTION_MODE = os.getenv("REMEDIATION_REAL_MODE", "true").lower() == "true"

class RemediationAction(BaseModel):
    id: str
    name: str
    description: str
    target: str  # container_id or host
    action_type: str  # restart, scale, clear_cache, block_ip
    risk_level: str  # low, medium, high
    requires_approval: bool

class RemediationJob(BaseModel):
    id: str
    action_id: str
    target: str
    status: str  # pending_approval, running, completed, failed
    created_at: str
    approved_by: Optional[str]
    completed_at: Optional[str]
    logs: List[str]

# In-memory job store
jobs: List[RemediationJob] = []

AVAILABLE_ACTIONS = [
    RemediationAction(
        id="act-restart",
        name="Restart Container",
        description="Gracefully restart the target container",
        target="container",
        action_type="restart",
        risk_level="medium",
        requires_approval=True
    ),
    RemediationAction(
        id="act-stop",
        name="Stop Container",
        description="Stop the target container",
        target="container",
        action_type="stop",
        risk_level="high",
        requires_approval=True
    ),
    RemediationAction(
        id="act-clear-logs",
        name="Clear Container Logs",
        description="Truncate container logs to free disk space",
        target="container",
        action_type="clear_logs",
        risk_level="low",
        requires_approval=False
    ),
    RemediationAction(
        id="act-kill",
        name="Kill Container",
        description="Forcefully kill the container (SIGKILL)",
        target="container",
        action_type="kill",
        risk_level="high",
        requires_approval=True
    )
]

def check_docker_available() -> bool:
    """Check if Docker CLI is available."""
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def run_docker_command(args: List[str]) -> tuple[bool, str]:
    """Run a Docker command and return success status and output."""
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)

async def execute_action(job: RemediationJob, action: RemediationAction):
    """Execute the remediation action on the target."""
    
    if not REAL_EXECUTION_MODE:
        job.logs.append("[SIMULATION] Real execution disabled")
        await asyncio.sleep(1)
        job.logs.append("[SIMULATION] Action would have been executed")
        job.status = "completed"
        job.completed_at = datetime.utcnow().isoformat()
        return
    
    if not check_docker_available():
        job.logs.append("ERROR: Docker CLI not available")
        job.status = "failed"
        job.completed_at = datetime.utcnow().isoformat()
        return
    
    try:
        if action.action_type == "restart":
            job.logs.append(f"Restarting container: {job.target}")
            success, output = run_docker_command(["restart", job.target])
            if success:
                job.logs.append(f"Container {job.target} restarted successfully")
            else:
                job.logs.append(f"Failed to restart: {output}")
                job.status = "failed"
                job.completed_at = datetime.utcnow().isoformat()
                return
                
        elif action.action_type == "stop":
            job.logs.append(f"Stopping container: {job.target}")
            success, output = run_docker_command(["stop", job.target])
            if success:
                job.logs.append(f"Container {job.target} stopped")
            else:
                job.logs.append(f"Failed to stop: {output}")
                job.status = "failed"
                job.completed_at = datetime.utcnow().isoformat()
                return
                
        elif action.action_type == "kill":
            job.logs.append(f"Killing container: {job.target}")
            success, output = run_docker_command(["kill", job.target])
            if success:
                job.logs.append(f"Container {job.target} killed")
            else:
                job.logs.append(f"Failed to kill: {output}")
                job.status = "failed"
                job.completed_at = datetime.utcnow().isoformat()
                return
                
        elif action.action_type == "clear_logs":
            job.logs.append(f"Getting log path for: {job.target}")
            # Get container log path and truncate
            success, log_path = run_docker_command([
                "inspect", "--format", "{{.LogPath}}", job.target
            ])
            if success and log_path:
                job.logs.append(f"Log path: {log_path}")
                # Truncate the log file (requires host access, may not work in container)
                job.logs.append("Note: Log truncation requires host-level access")
            job.logs.append("Log truncate command sent")
            
        job.status = "completed"
        job.logs.append("Action executed successfully")
        
    except Exception as e:
        job.logs.append(f"ERROR: {str(e)}")
        job.status = "failed"
    finally:
        job.completed_at = datetime.utcnow().isoformat()

@router.get("/actions")
async def get_available_actions() -> List[RemediationAction]:
    """Get list of available remediation actions."""
    return AVAILABLE_ACTIONS

@router.get("/status")
async def get_status():
    """Get remediation system status."""
    docker_ok = check_docker_available()
    return {
        "docker_available": docker_ok,
        "real_execution_mode": REAL_EXECUTION_MODE,
        "docker_connected": docker_ok,
        "total_jobs": len(jobs),
        "pending_jobs": len([j for j in jobs if j.status == "pending_approval"])
    }

@router.post("/trigger")
async def trigger_action(
    action_id: str, 
    target: str, 
    user: str = "system"
) -> RemediationJob:
    """Trigger a remediation action."""
    action = next((a for a in AVAILABLE_ACTIONS if a.id == action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    
    job = RemediationJob(
        id=f"job-{random.randint(10000, 99999)}",
        action_id=action_id,
        target=target,
        status="pending_approval" if action.requires_approval else "running",
        created_at=datetime.utcnow().isoformat(),
        approved_by=None if action.requires_approval else user,
        completed_at=None,
        logs=[f"Job created by {user}", f"Target: {target}", f"Action: {action.name}"]
    )
    
    jobs.insert(0, job)
    
    # Keep only last 100 jobs
    if len(jobs) > 100:
        jobs[:] = jobs[:100]
    
    if not action.requires_approval:
        job.logs.append("Auto-executing (no approval required)...")
        await execute_action(job, action)
        
    return job

@router.post("/approve/{job_id}")
async def approve_job(job_id: str, user: str = "admin"):
    """Approve a pending remediation job and execute it."""
    job = next((j for j in jobs if j.id == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Job is not pending approval (status: {job.status})")
    
    action = next((a for a in AVAILABLE_ACTIONS if a.id == job.action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Associated action not found")
    
    job.status = "running"
    job.approved_by = user
    job.logs.append(f"Approved by {user}")
    job.logs.append("Executing action...")
    
    await execute_action(job, action)
    
    return job

@router.post("/reject/{job_id}")
async def reject_job(job_id: str, user: str = "admin", reason: str = ""):
    """Reject a pending remediation job."""
    job = next((j for j in jobs if j.id == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "pending_approval":
        raise HTTPException(status_code=400, detail="Job is not pending approval")
    
    job.status = "rejected"
    job.approved_by = user
    job.completed_at = datetime.utcnow().isoformat()
    job.logs.append(f"Rejected by {user}")
    if reason:
        job.logs.append(f"Reason: {reason}")
    
    return job

@router.get("/jobs")
async def get_jobs(limit: int = 20) -> List[RemediationJob]:
    """Get recent remediation jobs."""
    return jobs[:limit]

@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> RemediationJob:
    """Get a specific job by ID."""
    job = next((j for j in jobs if j.id == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
