"""
Timezone utilities for AncientReport - All times use Asia/Tehran timezone
"""
from datetime import datetime, timezone
from typing import Optional
import pytz

# Asia/Tehran timezone
TEHRAN_TZ = pytz.timezone('Asia/Tehran')

def now() -> datetime:
    """Get current time in Asia/Tehran timezone"""
    return datetime.now(TEHRAN_TZ)

def to_tehran(dt: datetime) -> datetime:
    """Convert a datetime to Asia/Tehran timezone"""
    if dt.tzinfo is None:
        # Naive datetime - assume it's already in Tehran timezone
        return TEHRAN_TZ.localize(dt)
    else:
        # Timezone-aware datetime - convert to Tehran
        return dt.astimezone(TEHRAN_TZ)

def to_utc_for_query(dt: datetime) -> datetime:
    """Convert datetime to UTC for ClickHouse queries (ClickHouse stores in UTC)"""
    if dt.tzinfo is None:
        # Assume naive datetime is in Tehran timezone
        dt = TEHRAN_TZ.localize(dt)
    # Convert to UTC
    return dt.astimezone(timezone.utc)

def from_iso(iso_str: str) -> datetime:
    """Parse ISO string and convert to Tehran timezone"""
    # Handle 'Z' suffix (UTC)
    if iso_str.endswith('Z'):
        iso_str = iso_str.replace('Z', '+00:00')
    
    dt = datetime.fromisoformat(iso_str)
    
    # If timezone-aware, convert to Tehran
    if dt.tzinfo is not None:
        dt = dt.astimezone(TEHRAN_TZ)
    else:
        # Naive datetime - assume Tehran timezone
        dt = TEHRAN_TZ.localize(dt)
    
    return dt

def format_for_display(dt: datetime) -> str:
    """Format datetime for display in Tehran timezone - returns ISO format string compatible with JavaScript Date()"""
    tehran_dt = to_tehran(dt)
    # Return ISO format that JavaScript can parse correctly
    return tehran_dt.isoformat()

def format_for_chart(dt: datetime) -> str:
    """Format datetime for chart display - returns ISO format with timezone offset"""
    tehran_dt = to_tehran(dt)
    # Ensure it's a proper ISO string that JavaScript Date() can parse
    return tehran_dt.isoformat()


