"""
API endpoint for Docker container healthcheck status
"""
import os
import subprocess
import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from fastapi.logger import logger

router = APIRouter()

def get_docker_binary() -> str:
    """Find Docker binary in common locations"""
    common_paths = ["/usr/bin/docker", "/usr/local/bin/docker", "/bin/docker", "docker"]
    for path in common_paths:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, timeout=2)
            if result.returncode == 0:
                return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return "docker"  # Fallback to PATH

@router.get("/healthchecks", response_model=List[Dict[str, Any]])
async def get_container_healthchecks():
    """
    Get healthcheck status for all containers that have healthchecks configured.
    Returns only containers that have a healthcheck defined.
    """
    docker_path = get_docker_binary()
    
    try:
        # Get all container IDs
        ps_result = subprocess.run(
            [docker_path, "ps", "-a", "--format", "{{.ID}}|{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if ps_result.returncode != 0:
            logger.error(f"Docker ps failed: {ps_result.stderr}")
            raise HTTPException(status_code=500, detail="Failed to list containers")
        
        containers = []
        for line in ps_result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('|')
            if len(parts) < 2:
                continue
            
            container_id = parts[0].strip()
            container_name = parts[1].strip()
            
            # Check if container has healthcheck configured
            inspect_result = subprocess.run(
                [docker_path, "inspect", container_id, "--format", 
                 "{{.State.Health.Status}}|{{.Config.Healthcheck.Test}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if inspect_result.returncode != 0:
                # Container might not exist or no healthcheck
                continue
            
            health_data = inspect_result.stdout.strip()
            if not health_data or health_data == "none|":
                # No healthcheck configured
                continue
            
            parts = health_data.split('|')
            health_status = parts[0].strip() if len(parts) > 0 else "none"
            health_test = parts[1].strip() if len(parts) > 1 else ""
            
            # Only include containers with healthcheck (status != "none")
            if health_status == "none":
                continue
            
            # Get additional healthcheck details
            health_details = {}
            try:
                inspect_json = subprocess.run(
                    [docker_path, "inspect", container_id, "--format", "{{json .State.Health}}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if inspect_json.returncode == 0 and inspect_json.stdout.strip():
                    health_json = json.loads(inspect_json.stdout.strip())
                    if health_json:
                        health_details = {
                            "failing_streak": health_json.get("FailingStreak", 0),
                            "log": health_json.get("Log", [])
                        }
            except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
                logger.warning(f"Could not parse health details for {container_name}: {e}")
            
            containers.append({
                "id": container_id,
                "name": container_name,
                "health_status": health_status,  # starting, healthy, unhealthy
                "health_test": health_test,
                "failing_streak": health_details.get("failing_streak", 0),
                "last_log": health_details.get("log", [{}])[-1].get("Output", "") if health_details.get("log") else "",
                "hostname": os.uname().nodename
            })
        
        logger.info(f"Found {len(containers)} containers with healthchecks")
        return containers
        
    except subprocess.TimeoutExpired:
        logger.error("Docker command timed out")
        raise HTTPException(status_code=504, detail="Docker command timed out")
    except Exception as e:
        logger.error(f"Failed to get healthcheck status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

