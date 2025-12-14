"""
SNMP Monitoring API
Full-featured SNMP monitoring for network devices, servers, printers, UPS, etc.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4
import asyncio
import json
import logging

# SNMP library - using pysnmp
try:
    from pysnmp.hlapi.asyncio import (
        getCmd, nextCmd, bulkCmd,
        SnmpEngine, CommunityData, UsmUserData,
        UdpTransportTarget, ContextData,
        ObjectType, ObjectIdentity,
        usmHMACMD5AuthProtocol, usmHMACSHAAuthProtocol,
        usmDESPrivProtocol, usmAesCfb128Protocol
    )
    PYSNMP_AVAILABLE = True
except ImportError:
    PYSNMP_AVAILABLE = False
    logging.warning("pysnmp not available - SNMP features will be limited")

from storage.clickhouse_client import get_clickhouse_client

router = APIRouter(prefix="/api/snmp", tags=["SNMP Monitoring"])
logger = logging.getLogger(__name__)

def get_client():
    """Get ClickHouse client for queries"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    return client

# Module-level client for initialization
_clickhouse_client = None

def set_clickhouse_client(client):
    """Set ClickHouse client for the SNMP module (called from main.py at startup)"""
    global _clickhouse_client
    _clickhouse_client = client
    logger.info("SNMP module initialized with ClickHouse client")


# ============================================
# Pydantic Models
# ============================================

class SNMPDeviceCreate(BaseModel):
    name: str
    ip_address: str
    snmp_version: str = "v2c"
    community: str = "public"
    username: str = ""
    auth_protocol: str = ""
    auth_password: str = ""
    priv_protocol: str = ""
    priv_password: str = ""
    port: int = 161
    device_type: str = "unknown"
    vendor: str = ""
    template_id: Optional[str] = None
    poll_interval: int = 60
    timeout_ms: int = 5000
    retries: int = 3
    enabled: bool = True

class SNMPDeviceUpdate(BaseModel):
    name: Optional[str] = None
    community: Optional[str] = None
    snmp_version: Optional[str] = None
    username: Optional[str] = None
    auth_protocol: Optional[str] = None
    auth_password: Optional[str] = None
    priv_protocol: Optional[str] = None
    priv_password: Optional[str] = None
    port: Optional[int] = None
    device_type: Optional[str] = None
    vendor: Optional[str] = None
    template_id: Optional[str] = None
    poll_interval: Optional[int] = None
    timeout_ms: Optional[int] = None
    retries: Optional[int] = None
    enabled: Optional[bool] = None

class SNMPOIDCreate(BaseModel):
    oid: str
    name: str
    description: str = ""
    mib_name: str = ""
    data_type: str = "gauge"
    unit: str = ""
    multiplier: float = 1.0
    is_delta: bool = False
    poll_interval: int = 60
    enabled: bool = True

class SNMPTemplateCreate(BaseModel):
    name: str
    vendor: str
    device_type: str
    sys_object_id_pattern: str = ""
    description: str = ""
    oids: List[Dict[str, Any]] = []
    icon: str = "server"

class NetworkScanRequest(BaseModel):
    network: str  # e.g., "192.168.1.0/24"
    community: str = "public"
    snmp_version: str = "v2c"
    timeout_ms: int = 2000

# ============================================
# Standard OIDs
# ============================================

SYSTEM_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",
}

INTERFACE_OIDS = {
    "ifNumber": "1.3.6.1.2.1.2.1.0",
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",
    "ifType": "1.3.6.1.2.1.2.2.1.3",
    "ifMtu": "1.3.6.1.2.1.2.2.1.4",
    "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
    "ifPhysAddress": "1.3.6.1.2.1.2.2.1.6",
    "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
    "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
    "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
}

# ============================================
# SNMP Helper Functions
# ============================================

async def snmp_get(ip: str, oids: List[str], community: str = "public", 
                   port: int = 161, timeout: float = 5.0, retries: int = 3,
                   version: str = "v2c", **v3_params) -> Dict[str, Any]:
    """Perform SNMP GET operation"""
    if not PYSNMP_AVAILABLE:
        return {"error": "pysnmp not installed"}
    
    try:
        # Build auth data based on version
        if version == "v3":
            auth_proto = None
            priv_proto = None
            if v3_params.get("auth_protocol") == "MD5":
                auth_proto = usmHMACMD5AuthProtocol
            elif v3_params.get("auth_protocol") in ["SHA", "SHA1"]:
                auth_proto = usmHMACSHAAuthProtocol
            
            if v3_params.get("priv_protocol") == "DES":
                priv_proto = usmDESPrivProtocol
            elif v3_params.get("priv_protocol") in ["AES", "AES128"]:
                priv_proto = usmAesCfb128Protocol
            
            auth_data = UsmUserData(
                v3_params.get("username", ""),
                authKey=v3_params.get("auth_password", "") or None,
                privKey=v3_params.get("priv_password", "") or None,
                authProtocol=auth_proto,
                privProtocol=priv_proto
            )
        else:
            mp_model = 1 if version == "v2c" else 0
            auth_data = CommunityData(community, mpModel=mp_model)
        
        # Build object types
        var_binds = [ObjectType(ObjectIdentity(oid)) for oid in oids]
        
        # Perform GET
        engine = SnmpEngine()
        result = await getCmd(
            engine,
            auth_data,
            UdpTransportTarget((ip, port), timeout=timeout, retries=retries),
            ContextData(),
            *var_binds
        )
        
        errorIndication, errorStatus, errorIndex, varBinds = result
        
        if errorIndication:
            return {"error": str(errorIndication)}
        elif errorStatus:
            return {"error": f"{errorStatus.prettyPrint()} at {errorIndex}"}
        
        # Parse results
        values = {}
        for varBind in varBinds:
            oid = str(varBind[0])
            value = varBind[1]
            # Convert pysnmp types to Python types
            try:
                if hasattr(value, 'prettyPrint'):
                    values[oid] = value.prettyPrint()
                else:
                    values[oid] = str(value)
            except:
                values[oid] = str(value)
        
        return {"success": True, "values": values}
        
    except Exception as e:
        logger.error(f"SNMP GET error for {ip}: {e}")
        return {"error": str(e)}

async def snmp_walk(ip: str, base_oid: str, community: str = "public",
                    port: int = 161, timeout: float = 5.0, retries: int = 3,
                    version: str = "v2c", max_rows: int = 1000, **v3_params) -> Dict[str, Any]:
    """Perform SNMP WALK operation"""
    if not PYSNMP_AVAILABLE:
        return {"error": "pysnmp not installed"}
    
    try:
        if version == "v3":
            auth_data = UsmUserData(
                v3_params.get("username", ""),
                authKey=v3_params.get("auth_password", "") or None,
                privKey=v3_params.get("priv_password", "") or None
            )
        else:
            mp_model = 1 if version == "v2c" else 0
            auth_data = CommunityData(community, mpModel=mp_model)
        
        engine = SnmpEngine()
        values = {}
        count = 0
        
        async for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
            engine,
            auth_data,
            UdpTransportTarget((ip, port), timeout=timeout, retries=retries),
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False
        ):
            if errorIndication:
                return {"error": str(errorIndication)}
            elif errorStatus:
                return {"error": f"{errorStatus.prettyPrint()} at {errorIndex}"}
            
            for varBind in varBinds:
                oid = str(varBind[0])
                value = varBind[1]
                try:
                    values[oid] = value.prettyPrint() if hasattr(value, 'prettyPrint') else str(value)
                except:
                    values[oid] = str(value)
            
            count += 1
            if count >= max_rows:
                break
        
        return {"success": True, "values": values, "count": len(values)}
        
    except Exception as e:
        logger.error(f"SNMP WALK error for {ip}: {e}")
        return {"error": str(e)}

# ============================================
# Device Endpoints
# ============================================

@router.get("/devices")
async def list_devices():
    """List all SNMP devices"""
    try:
        client = get_client()
        rows = client.client.execute("""
            SELECT 
                id, name, ip_address, snmp_version, port,
                device_type, vendor, model, sys_name, sys_location,
                enabled, poll_interval, status, sys_uptime,
                last_poll, last_success, error_message,
                created_at, updated_at
            FROM snmp_devices
            FINAL
            ORDER BY name
        """)
        
        devices = []
        for row in rows:
            devices.append({
                "id": str(row[0]),
                "name": row[1],
                "ip_address": row[2],
                "snmp_version": row[3],
                "port": row[4],
                "device_type": row[5],
                "vendor": row[6],
                "model": row[7],
                "sys_name": row[8],
                "sys_location": row[9],
                "enabled": bool(row[10]),
                "poll_interval": row[11],
                "status": row[12],
                "sys_uptime": row[13],
                "last_poll": row[14].isoformat() if row[14] else None,
                "last_success": row[15].isoformat() if row[15] else None,
                "error_message": row[16],
                "created_at": row[17].isoformat() if row[17] else None,
                "updated_at": row[18].isoformat() if row[18] else None
            })
        
        return devices
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/devices")
async def create_device(device: SNMPDeviceCreate, background_tasks: BackgroundTasks):
    """Add a new SNMP device"""
    try:
        device_id = str(uuid4())
        
        get_client().client.execute(f"""
            INSERT INTO snmp_devices (
                id, name, ip_address, snmp_version, community,
                username, auth_protocol, auth_password,
                priv_protocol, priv_password, port,
                device_type, vendor, template_id,
                enabled, poll_interval, timeout_ms, retries,
                status
            ) VALUES (
                '{device_id}', '{device.name}', '{device.ip_address}',
                '{device.snmp_version}', '{device.community}',
                '{device.username}', '{device.auth_protocol}', '{device.auth_password}',
                '{device.priv_protocol}', '{device.priv_password}', {device.port},
                '{device.device_type}', '{device.vendor}',
                {'NULL' if not device.template_id else f"'{device.template_id}'"},
                {1 if device.enabled else 0}, {device.poll_interval},
                {device.timeout_ms}, {device.retries},
                'unknown'
            )
        """)
        
        # Schedule initial poll in background
        background_tasks.add_task(poll_device_task, device_id)
        
        return {"id": device_id, "message": "Device created, initial poll scheduled"}
    except Exception as e:
        logger.error(f"Failed to create device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/devices/{device_id}")
async def get_device(device_id: str):
    """Get device details"""
    try:
        result = get_client().client.execute(f"""
            SELECT *
            FROM snmp_devices
            FINAL
            WHERE id = '{device_id}'
        """)
        
        if not result:
            raise HTTPException(status_code=404, detail="Device not found")
        
        row = result[0]
        cols = result.column_names
        device = {cols[i]: row[i] for i in range(len(cols))}
        
        # Convert types
        device['id'] = str(device['id'])
        device['enabled'] = bool(device.get('enabled', 0))
        for dt_field in ['last_poll', 'last_success', 'created_at', 'updated_at']:
            if device.get(dt_field):
                device[dt_field] = device[dt_field].isoformat()
        
        return device
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/devices/{device_id}")
async def update_device(device_id: str, update: SNMPDeviceUpdate):
    """Update device settings"""
    try:
        updates = []
        for field, value in update.dict(exclude_unset=True).items():
            if value is not None:
                if isinstance(value, bool):
                    updates.append(f"{field} = {1 if value else 0}")
                elif isinstance(value, str):
                    updates.append(f"{field} = '{value}'")
                else:
                    updates.append(f"{field} = {value}")
        
        if updates:
            updates.append("updated_at = now()")
            get_client().client.execute(f"""
                ALTER TABLE snmp_devices
                UPDATE {', '.join(updates)}
                WHERE id = '{device_id}'
            """)
        
        return {"message": "Device updated"}
    except Exception as e:
        logger.error(f"Failed to update device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/devices/{device_id}")
async def delete_device(device_id: str):
    """Delete a device and its data"""
    try:
        # Delete device
        get_client().client.execute(f"DELETE FROM snmp_devices WHERE id = '{device_id}'")
        # Delete OIDs
        get_client().client.execute(f"DELETE FROM snmp_oids WHERE device_id = '{device_id}'")
        # Delete metrics
        get_client().client.execute(f"DELETE FROM snmp_metrics WHERE device_id = '{device_id}'")
        # Delete interfaces
        get_client().client.execute(f"DELETE FROM snmp_interfaces WHERE device_id = '{device_id}'")
        
        return {"message": "Device and related data deleted"}
    except Exception as e:
        logger.error(f"Failed to delete device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/devices/{device_id}/test")
async def test_device(device_id: str):
    """Test SNMP connectivity to device"""
    try:
        # Get device info
        result = get_client().client.execute(f"""
            SELECT ip_address, community, snmp_version, port, timeout_ms, retries,
                   username, auth_protocol, auth_password, priv_protocol, priv_password
            FROM snmp_devices FINAL WHERE id = '{device_id}'
        """)
        
        if not result:
            raise HTTPException(status_code=404, detail="Device not found")
        
        row = result[0]
        ip, community, version, port, timeout, retries = row[0:6]
        v3_params = {
            "username": row[6],
            "auth_protocol": row[7],
            "auth_password": row[8],
            "priv_protocol": row[9],
            "priv_password": row[10]
        }
        
        # Test with sysDescr
        oids = list(SYSTEM_OIDS.values())
        result = await snmp_get(ip, oids, community, port, timeout/1000, retries, version, **v3_params)
        
        if "error" in result:
            return {"success": False, "error": result["error"]}
        
        return {
            "success": True,
            "response_time_ms": 100,  # TODO: measure actual time
            "system_info": result.get("values", {})
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return {"success": False, "error": str(e)}

@router.post("/devices/{device_id}/poll")
async def poll_device(device_id: str, background_tasks: BackgroundTasks):
    """Manually trigger a poll for device"""
    background_tasks.add_task(poll_device_task, device_id)
    return {"message": "Poll scheduled"}

@router.post("/devices/{device_id}/walk")
async def walk_device(device_id: str, base_oid: str = "1.3.6.1.2.1"):
    """SNMP walk from a base OID"""
    try:
        # Get device info
        result = get_client().client.execute(f"""
            SELECT ip_address, community, snmp_version, port, timeout_ms, retries
            FROM snmp_devices FINAL WHERE id = '{device_id}'
        """)
        
        if not result:
            raise HTTPException(status_code=404, detail="Device not found")
        
        row = result[0]
        ip, community, version, port, timeout, retries = row
        
        walk_result = await snmp_walk(ip, base_oid, community, port, timeout/1000, retries, version)
        
        return walk_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Walk failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# OID Endpoints
# ============================================

@router.get("/oids/{device_id}")
async def list_device_oids(device_id: str):
    """List OIDs configured for a device"""
    try:
        result = get_client().client.execute(f"""
            SELECT id, oid, name, description, mib_name, data_type, unit,
                   multiplier, is_delta, enabled, poll_interval, last_value, last_poll
            FROM snmp_oids
            FINAL
            WHERE device_id = '{device_id}'
            ORDER BY name
        """)
        
        oids = []
        for row in result:
            oids.append({
                "id": str(row[0]),
                "oid": row[1],
                "name": row[2],
                "description": row[3],
                "mib_name": row[4],
                "data_type": row[5],
                "unit": row[6],
                "multiplier": row[7],
                "is_delta": bool(row[8]),
                "enabled": bool(row[9]),
                "poll_interval": row[10],
                "last_value": row[11],
                "last_poll": row[12].isoformat() if row[12] else None
            })
        
        return oids
    except Exception as e:
        logger.error(f"Failed to list OIDs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/oids/{device_id}")
async def add_device_oid(device_id: str, oid_def: SNMPOIDCreate):
    """Add an OID to monitor for a device"""
    try:
        oid_id = str(uuid4())
        
        get_client().client.execute(f"""
            INSERT INTO snmp_oids (
                id, device_id, oid, name, description, mib_name,
                data_type, unit, multiplier, is_delta, enabled, poll_interval
            ) VALUES (
                '{oid_id}', '{device_id}', '{oid_def.oid}', '{oid_def.name}',
                '{oid_def.description}', '{oid_def.mib_name}', '{oid_def.data_type}',
                '{oid_def.unit}', {oid_def.multiplier}, {1 if oid_def.is_delta else 0},
                {1 if oid_def.enabled else 0}, {oid_def.poll_interval}
            )
        """)
        
        return {"id": oid_id, "message": "OID added"}
    except Exception as e:
        logger.error(f"Failed to add OID: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/oids/{oid_id}")
async def delete_oid(oid_id: str):
    """Delete an OID"""
    try:
        get_client().client.execute(f"DELETE FROM snmp_oids WHERE id = '{oid_id}'")
        return {"message": "OID deleted"}
    except Exception as e:
        logger.error(f"Failed to delete OID: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# Metrics Endpoints
# ============================================

@router.get("/metrics/{device_id}")
async def get_device_metrics(device_id: str, hours: int = 1, oid: Optional[str] = None):
    """Get polled metrics for a device"""
    try:
        oid_filter = f"AND oid = '{oid}'" if oid else ""
        
        result = get_client().client.execute(f"""
            SELECT timestamp, oid, oid_name, value, value_string, data_type, unit
            FROM snmp_metrics
            WHERE device_id = '{device_id}'
            AND timestamp >= now() - INTERVAL {hours} HOUR
            {oid_filter}
            ORDER BY timestamp DESC
            LIMIT 10000
        """)
        
        metrics = []
        for row in result:
            metrics.append({
                "timestamp": row[0].isoformat(),
                "oid": row[1],
                "oid_name": row[2],
                "value": row[3],
                "value_string": row[4],
                "data_type": row[5],
                "unit": row[6]
            })
        
        return {"metrics": metrics, "count": len(metrics)}
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics/{device_id}/latest")
async def get_latest_metrics(device_id: str):
    """Get latest value for each OID"""
    try:
        result = get_client().client.execute(f"""
            SELECT oid, oid_name, value, value_string, unit, max(timestamp) as ts
            FROM snmp_metrics
            WHERE device_id = '{device_id}'
            AND timestamp >= now() - INTERVAL 1 DAY
            GROUP BY oid, oid_name, value, value_string, unit
            ORDER BY ts DESC
        """)
        
        metrics = {}
        for row in result:
            oid = row[0]
            if oid not in metrics:
                metrics[oid] = {
                    "oid": oid,
                    "name": row[1],
                    "value": row[2],
                    "value_string": row[3],
                    "unit": row[4],
                    "timestamp": row[5].isoformat()
                }
        
        return list(metrics.values())
    except Exception as e:
        logger.error(f"Failed to get latest metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# Templates Endpoints
# ============================================

@router.get("/templates")
async def list_templates():
    """List device templates"""
    try:
        result = get_client().client.execute("""
            SELECT id, name, vendor, device_type, sys_object_id_pattern,
                   description, oids, icon, created_at
            FROM snmp_templates
            FINAL
            ORDER BY vendor, name
        """)
        
        templates = []
        for row in result:
            templates.append({
                "id": str(row[0]),
                "name": row[1],
                "vendor": row[2],
                "device_type": row[3],
                "sys_object_id_pattern": row[4],
                "description": row[5],
                "oids": json.loads(row[6]) if row[6] else [],
                "icon": row[7],
                "created_at": row[8].isoformat() if row[8] else None
            })
        
        return templates
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/templates")
async def create_template(template: SNMPTemplateCreate):
    """Create a device template"""
    try:
        template_id = str(uuid4())
        oids_json = json.dumps(template.oids).replace("'", "''")
        
        get_client().client.execute(f"""
            INSERT INTO snmp_templates (
                id, name, vendor, device_type, sys_object_id_pattern,
                description, oids, icon
            ) VALUES (
                '{template_id}', '{template.name}', '{template.vendor}',
                '{template.device_type}', '{template.sys_object_id_pattern}',
                '{template.description}', '{oids_json}', '{template.icon}'
            )
        """)
        
        return {"id": template_id, "message": "Template created"}
    except Exception as e:
        logger.error(f"Failed to create template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/templates/{template_id}/apply/{device_id}")
async def apply_template(template_id: str, device_id: str):
    """Apply a template to a device (adds OIDs)"""
    try:
        # Get template OIDs
        result = get_client().client.execute(f"""
            SELECT oids FROM snmp_templates FINAL WHERE id = '{template_id}'
        """)
        
        if not result:
            raise HTTPException(status_code=404, detail="Template not found")
        
        oids = json.loads(result[0][0] or "[]")
        
        # Add each OID to device
        for oid_def in oids:
            oid_id = str(uuid4())
            get_client().client.execute(f"""
                INSERT INTO snmp_oids (
                    id, device_id, oid, name, description, mib_name,
                    data_type, unit, multiplier, is_delta, enabled
                ) VALUES (
                    '{oid_id}', '{device_id}', '{oid_def.get("oid", "")}',
                    '{oid_def.get("name", "")}', '{oid_def.get("description", "")}',
                    '{oid_def.get("mib_name", "")}', '{oid_def.get("data_type", "gauge")}',
                    '{oid_def.get("unit", "")}', {oid_def.get("multiplier", 1.0)},
                    {1 if oid_def.get("is_delta") else 0}, 1
                )
            """)
        
        # Update device template_id
        get_client().client.execute(f"""
            ALTER TABLE snmp_devices
            UPDATE template_id = '{template_id}', updated_at = now()
            WHERE id = '{device_id}'
        """)
        
        return {"message": f"Applied {len(oids)} OIDs from template"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# Traps Endpoints
# ============================================

@router.get("/traps")
async def list_traps(hours: int = 24, severity: Optional[str] = None, 
                     acknowledged: Optional[bool] = None, limit: int = 100):
    """List received SNMP traps"""
    try:
        filters = [f"timestamp >= now() - INTERVAL {hours} HOUR"]
        if severity:
            filters.append(f"severity = '{severity}'")
        if acknowledged is not None:
            filters.append(f"acknowledged = {1 if acknowledged else 0}")
        
        where_clause = " AND ".join(filters)
        
        result = get_client().client.execute(f"""
            SELECT id, timestamp, source_ip, device_id, device_name,
                   trap_oid, trap_name, trap_type, severity, message,
                   varbinds, acknowledged, acknowledged_by, acknowledged_at
            FROM snmp_traps
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT {limit}
        """)
        
        traps = []
        for row in result:
            traps.append({
                "id": str(row[0]),
                "timestamp": row[1].isoformat(),
                "source_ip": row[2],
                "device_id": str(row[3]) if row[3] else None,
                "device_name": row[4],
                "trap_oid": row[5],
                "trap_name": row[6],
                "trap_type": row[7],
                "severity": row[8],
                "message": row[9],
                "varbinds": json.loads(row[10]) if row[10] else {},
                "acknowledged": bool(row[11]),
                "acknowledged_by": row[12],
                "acknowledged_at": row[13].isoformat() if row[13] else None
            })
        
        return {"traps": traps, "count": len(traps)}
    except Exception as e:
        logger.error(f"Failed to list traps: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/traps/{trap_id}/ack")
async def acknowledge_trap(trap_id: str, user: str = "admin"):
    """Acknowledge a trap"""
    try:
        get_client().client.execute(f"""
            ALTER TABLE snmp_traps
            UPDATE acknowledged = 1, acknowledged_by = '{user}', acknowledged_at = now()
            WHERE id = '{trap_id}'
        """)
        return {"message": "Trap acknowledged"}
    except Exception as e:
        logger.error(f"Failed to acknowledge trap: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# Background Polling Task
# ============================================

async def poll_device_task(device_id: str):
    """Background task to poll a single device"""
    try:
        # Get device info
        result = get_client().client.execute(f"""
            SELECT ip_address, community, snmp_version, port, timeout_ms, retries, name,
                   username, auth_protocol, auth_password, priv_protocol, priv_password
            FROM snmp_devices FINAL WHERE id = '{device_id}'
        """)
        
        if not result:
            return
        
        row = result[0]
        ip, community, version, port, timeout, retries, name = row[0:7]
        v3_params = {
            "username": row[7],
            "auth_protocol": row[8],
            "auth_password": row[9],
            "priv_protocol": row[10],
            "priv_password": row[11]
        }
        
        # First, get system info
        sys_result = await snmp_get(ip, list(SYSTEM_OIDS.values()), community, port, 
                                     timeout/1000, retries, version, **v3_params)
        
        if "error" in sys_result:
            # Update device status to down
            get_client().client.execute(f"""
                ALTER TABLE snmp_devices
                UPDATE status = 'down', error_message = '{sys_result["error"]}', 
                       last_poll = now(), updated_at = now()
                WHERE id = '{device_id}'
            """)
            return
        
        # Extract system values
        values = sys_result.get("values", {})
        sys_descr = values.get(SYSTEM_OIDS["sysDescr"], "")
        sys_name = values.get(SYSTEM_OIDS["sysName"], "")
        sys_location = values.get(SYSTEM_OIDS["sysLocation"], "")
        sys_contact = values.get(SYSTEM_OIDS["sysContact"], "")
        sys_object_id = values.get(SYSTEM_OIDS["sysObjectID"], "")
        sys_uptime_raw = values.get(SYSTEM_OIDS["sysUpTime"], "0")
        
        # Parse uptime (timeticks = 1/100th seconds)
        try:
            sys_uptime = int(sys_uptime_raw) // 100 if sys_uptime_raw.isdigit() else 0
        except:
            sys_uptime = 0
        
        # Update device with system info
        get_client().client.execute(f"""
            ALTER TABLE snmp_devices
            UPDATE status = 'up', error_message = '',
                   sys_descr = '{sys_descr[:500].replace("'", "''")}',
                   sys_name = '{sys_name.replace("'", "''")}',
                   sys_location = '{sys_location.replace("'", "''")}',
                   sys_contact = '{sys_contact.replace("'", "''")}',
                   sys_object_id = '{sys_object_id}',
                   sys_uptime = {sys_uptime},
                   last_poll = now(), last_success = now(), updated_at = now()
            WHERE id = '{device_id}'
        """)
        
        # Poll configured OIDs
        oid_result = get_client().client.execute(f"""
            SELECT id, oid, name, data_type, unit, multiplier
            FROM snmp_oids FINAL
            WHERE device_id = '{device_id}' AND enabled = 1
        """)
        
        if oid_result:
            oids_to_poll = [row[1] for row in oid_result]
            oid_info = {row[1]: {"id": row[0], "name": row[2], "type": row[3], "unit": row[4], "mult": row[5]} 
                        for row in oid_result}
            
            poll_result = await snmp_get(ip, oids_to_poll, community, port, 
                                          timeout/1000, retries, version, **v3_params)
            
            if "values" in poll_result:
                for oid, value in poll_result["values"].items():
                    info = oid_info.get(oid, {})
                    try:
                        numeric_value = float(value) * info.get("mult", 1.0)
                    except:
                        numeric_value = 0.0
                    
                    # Insert metric
                    get_client().client.execute(f"""
                        INSERT INTO snmp_metrics (
                            timestamp, device_id, device_name, oid, oid_name,
                            value, value_string, data_type, unit
                        ) VALUES (
                            now(), '{device_id}', '{name}', '{oid}', '{info.get("name", oid)}',
                            {numeric_value}, '{value[:100]}', '{info.get("type", "gauge")}', '{info.get("unit", "")}'
                        )
                    """)
        
        logger.info(f"Successfully polled device {name} ({ip})")
        
    except Exception as e:
        logger.error(f"Poll task error for {device_id}: {e}")

# Background polling loop
_polling_task = None

async def start_polling_loop():
    """Start the background polling loop"""
    global _polling_task
    
    async def polling_loop():
        while True:
            try:
                # Get devices due for polling
                result = get_client().client.execute("""
                    SELECT id, poll_interval, last_poll
                    FROM snmp_devices FINAL
                    WHERE enabled = 1
                """)
                
                now = datetime.now()  # Use local time to match ClickHouse
                logger.debug(f"Polling loop checking {len(result)} devices at {now}")
                for row in result:
                    device_id = str(row[0])
                    interval = row[1]
                    last_poll = row[2]
                    
                    # Check if due for polling
                    if last_poll is None or (now - last_poll).total_seconds() >= interval:
                        logger.info(f"Device {device_id} due for poll (last: {last_poll}, interval: {interval}s)")
                        asyncio.create_task(poll_device_task(device_id))
                
            except Exception as e:
                logger.error(f"Polling loop error: {e}")
            
            await asyncio.sleep(10)  # Check every 10 seconds
    
    _polling_task = asyncio.create_task(polling_loop())
    logger.info("SNMP polling loop started")

async def stop_polling_loop():
    """Stop the polling loop"""
    global _polling_task
    if _polling_task:
        _polling_task.cancel()
        _polling_task = None

# ============================================
# Initialize Default Templates
# ============================================

DEFAULT_TEMPLATES = [
    {
        "name": "Cisco Router",
        "vendor": "Cisco",
        "device_type": "router",
        "icon": "router",
        "description": "Standard OIDs for Cisco routers",
        "oids": [
            {"oid": "1.3.6.1.4.1.9.2.1.57.0", "name": "cpu_5min", "unit": "%", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.9.9.48.1.1.1.5.1", "name": "mem_used", "unit": "bytes", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.9.9.48.1.1.1.6.1", "name": "mem_free", "unit": "bytes", "data_type": "gauge"},
        ]
    },
    {
        "name": "Linux Server (net-snmp)",
        "vendor": "Linux",
        "device_type": "server",
        "icon": "server",
        "description": "Standard OIDs for Linux servers with net-snmp",
        "oids": [
            {"oid": "1.3.6.1.4.1.2021.11.9.0", "name": "cpu_user", "unit": "%", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.2021.11.10.0", "name": "cpu_system", "unit": "%", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.2021.11.11.0", "name": "cpu_idle", "unit": "%", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.2021.4.5.0", "name": "mem_total", "unit": "KB", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.2021.4.6.0", "name": "mem_avail", "unit": "KB", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.2021.4.14.0", "name": "mem_buffered", "unit": "KB", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.2021.4.15.0", "name": "mem_cached", "unit": "KB", "data_type": "gauge"},
        ]
    },
    {
        "name": "APC UPS",
        "vendor": "APC",
        "device_type": "ups",
        "icon": "battery",
        "description": "APC UPS monitoring",
        "oids": [
            {"oid": "1.3.6.1.4.1.318.1.1.1.2.2.1.0", "name": "battery_capacity", "unit": "%", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.318.1.1.1.2.2.2.0", "name": "battery_temp", "unit": "°C", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.318.1.1.1.2.2.3.0", "name": "runtime_remaining", "unit": "min", "data_type": "gauge", "multiplier": 0.01},
            {"oid": "1.3.6.1.4.1.318.1.1.1.4.2.1.0", "name": "output_voltage", "unit": "V", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.318.1.1.1.4.2.3.0", "name": "output_load", "unit": "%", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.318.1.1.1.3.2.1.0", "name": "input_voltage", "unit": "V", "data_type": "gauge"},
        ]
    },
    {
        "name": "HP ProCurve Switch",
        "vendor": "HP",
        "device_type": "switch",
        "icon": "network",
        "description": "HP ProCurve switch monitoring",
        "oids": [
            {"oid": "1.3.6.1.4.1.11.2.14.11.5.1.9.6.1.0", "name": "cpu_util", "unit": "%", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.5.1", "name": "mem_total", "unit": "bytes", "data_type": "gauge"},
            {"oid": "1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.6.1", "name": "mem_free", "unit": "bytes", "data_type": "gauge"},
        ]
    },
    {
        "name": "Generic Printer",
        "vendor": "Generic",
        "device_type": "printer",
        "icon": "printer",
        "description": "Standard printer MIB OIDs",
        "oids": [
            {"oid": "1.3.6.1.2.1.43.10.2.1.4.1.1", "name": "total_pages", "unit": "pages", "data_type": "counter"},
            {"oid": "1.3.6.1.2.1.43.11.1.1.9.1.1", "name": "toner_level", "unit": "%", "data_type": "gauge"},
            {"oid": "1.3.6.1.2.1.43.11.1.1.8.1.1", "name": "toner_max", "unit": "", "data_type": "gauge"},
        ]
    },
]

async def initialize_default_templates():
    """Create default templates if they don't exist"""
    try:
        # Check if templates exist
        result = get_client().client.execute("SELECT count() FROM snmp_templates")
        if result[0][0] > 0:
            return  # Templates already exist
        
        for tmpl in DEFAULT_TEMPLATES:
            template_id = str(uuid4())
            oids_json = json.dumps(tmpl["oids"]).replace("'", "''")
            
            get_client().client.execute(f"""
                INSERT INTO snmp_templates (
                    id, name, vendor, device_type, description, oids, icon
                ) VALUES (
                    '{template_id}', '{tmpl["name"]}', '{tmpl["vendor"]}',
                    '{tmpl["device_type"]}', '{tmpl["description"]}',
                    '{oids_json}', '{tmpl["icon"]}'
                )
            """)
        
        logger.info(f"Initialized {len(DEFAULT_TEMPLATES)} default SNMP templates")
    except Exception as e:
        logger.error(f"Failed to initialize templates: {e}")


# ============================================
# SNMP Alert Models and Endpoints
# ============================================

class SNMPAlertCreate(BaseModel):
    device_id: str
    oid_name: str  # e.g. "Disk Usage", "CPU Load"
    condition: str = ">"  # >, <, >=, <=, ==, !=
    threshold: float
    severity: str = "warning"  # info, warning, critical
    message: str = ""
    enabled: bool = True

class SNMPAlertUpdate(BaseModel):
    condition: Optional[str] = None
    threshold: Optional[float] = None
    severity: Optional[str] = None
    message: Optional[str] = None
    enabled: Optional[bool] = None

@router.get("/alerts")
async def list_snmp_alerts(device_id: Optional[str] = None):
    """List SNMP alerts"""
    try:
        device_filter = f"AND device_id = '{device_id}'" if device_id else ""
        
        rows = get_client().client.execute(f"""
            SELECT id, device_id, oid_name, condition, threshold, 
                   severity, message, enabled, last_triggered, created_at
            FROM snmp_alerts
            FINAL
            WHERE 1=1 {device_filter}
            ORDER BY severity DESC, oid_name
        """)
        
        alerts = []
        for row in rows:
            alerts.append({
                "id": str(row[0]),
                "device_id": str(row[1]),
                "oid_name": row[2],
                "condition": row[3],
                "threshold": row[4],
                "severity": row[5],
                "message": row[6],
                "enabled": bool(row[7]),
                "last_triggered": row[8].isoformat() if row[8] else None,
                "created_at": row[9].isoformat() if row[9] else None
            })
        
        return alerts
    except Exception as e:
        if "doesn't exist" in str(e) or "Unknown table" in str(e):
            return []  # Table not created yet
        logger.error(f"Failed to list alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/alerts")
async def create_snmp_alert(alert: SNMPAlertCreate):
    """Create an SNMP alert threshold"""
    try:
        alert_id = str(uuid4())
        
        # Ensure snmp_alerts table exists
        get_client().client.execute("""
            CREATE TABLE IF NOT EXISTS snmp_alerts (
                id UUID,
                device_id UUID,
                oid_name String,
                condition String,
                threshold Float64,
                severity String,
                message String,
                enabled UInt8,
                last_triggered Nullable(DateTime),
                created_at DateTime
            ) ENGINE = ReplacingMergeTree ORDER BY id
        """)
        
        get_client().client.execute(f"""
            INSERT INTO snmp_alerts (
                id, device_id, oid_name, condition, threshold,
                severity, message, enabled, created_at
            ) VALUES (
                '{alert_id}', '{alert.device_id}', '{alert.oid_name}',
                '{alert.condition}', {alert.threshold}, '{alert.severity}',
                '{alert.message}', {1 if alert.enabled else 0}, now()
            )
        """)
        
        return {"id": alert_id, "message": "Alert created"}
    except Exception as e:
        logger.error(f"Failed to create alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/alerts/{alert_id}")
async def delete_snmp_alert(alert_id: str):
    """Delete an SNMP alert"""
    try:
        get_client().client.execute(f"DELETE FROM snmp_alerts WHERE id = '{alert_id}'")
        return {"message": "Alert deleted"}
    except Exception as e:
        logger.error(f"Failed to delete alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts/check/{device_id}")
async def check_device_alerts(device_id: str):
    """Check all alerts for a device against latest metrics"""
    try:
        # Get alerts for device
        alerts = get_client().client.execute(f"""
            SELECT id, oid_name, condition, threshold, severity, message
            FROM snmp_alerts FINAL
            WHERE device_id = '{device_id}' AND enabled = 1
        """)
        
        if not alerts:
            return {"triggered": [], "message": "No alerts configured"}
        
        # Get latest metrics
        metrics = get_client().client.execute(f"""
            SELECT oid_name, value
            FROM snmp_metrics
            WHERE device_id = '{device_id}'
            AND timestamp >= now() - INTERVAL 5 MINUTE
            ORDER BY timestamp DESC
            LIMIT 100
        """)
        
        # Build metric lookup
        metric_values = {}
        for m in metrics:
            if m[0] not in metric_values:
                metric_values[m[0]] = m[1]
        
        # Check each alert
        triggered = []
        for alert in alerts:
            alert_id, oid_name, condition, threshold, severity, message = alert
            value = metric_values.get(oid_name)
            
            if value is None:
                continue
            
            # Evaluate condition
            is_triggered = False
            if condition == ">" and value > threshold:
                is_triggered = True
            elif condition == "<" and value < threshold:
                is_triggered = True
            elif condition == ">=" and value >= threshold:
                is_triggered = True
            elif condition == "<=" and value <= threshold:
                is_triggered = True
            elif condition == "==" and value == threshold:
                is_triggered = True
            elif condition == "!=" and value != threshold:
                is_triggered = True
            
            if is_triggered:
                triggered.append({
                    "alert_id": str(alert_id),
                    "oid_name": oid_name,
                    "condition": f"{condition} {threshold}",
                    "current_value": value,
                    "severity": severity,
                    "message": message or f"{oid_name} is {value} ({condition} {threshold})"
                })
                
                # Update last_triggered
                get_client().client.execute(f"""
                    ALTER TABLE snmp_alerts
                    UPDATE last_triggered = now()
                    WHERE id = '{alert_id}'
                """)
        
        return {
            "triggered": triggered,
            "checked_alerts": len(alerts),
            "metrics_available": len(metric_values)
        }
    except Exception as e:
        logger.error(f"Failed to check alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

