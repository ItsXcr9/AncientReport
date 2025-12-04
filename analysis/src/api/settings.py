"""
Settings API - Manage application configuration
"""
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)
router = APIRouter()


class Setting(BaseModel):
    """Setting model"""
    setting_key: str
    setting_value: str
    category: str
    description: Optional[str] = None
    is_encrypted: bool = False


class SettingsUpdate(BaseModel):
    """Settings update payload"""
    settings: Dict[str, str]


@router.get("/settings")
async def get_all_settings():
    """
    Get all settings grouped by category
    
    Returns settings with sensitive values masked
    """
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT 
            setting_key,
            setting_value,
            category,
            description,
            is_encrypted,
            updated_at
        FROM AncientReport.settings
        FINAL
        ORDER BY category, setting_key
        """
        
        result = ch.query(query)
        
        # Group by category
        settings_by_category = {}
        for row in result:
            category = row['category']
            if category not in settings_by_category:
                settings_by_category[category] = []
            
            # Mask sensitive values
            value = row['setting_value']
            if row['is_encrypted'] or 'token' in row['setting_key'] or 'key' in row['setting_key']:
                if value and len(value) > 4:
                    value = value[:4] + '*' * (len(value) - 4)
            
            settings_by_category[category].append({
                'key': row['setting_key'],
                'value': value,
                'description': row['description'],
                'is_encrypted': row['is_encrypted'],
                'updated_at': row['updated_at'].isoformat()
            })
        
        return {
            'status': 'success',
            'settings': settings_by_category
        }
        
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/{category}")
async def get_settings_by_category(category: str):
    """Get settings for a specific category"""
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT 
            setting_key,
            setting_value,
            category,
            description,
            is_encrypted
        FROM AncientReport.settings
        FINAL
        WHERE category = %(category)s
        ORDER BY setting_key
        """
        
        result = ch.query(query, {'category': category})
        
        settings = []
        for row in result:
            # Mask sensitive values
            value = row['setting_value']
            if row['is_encrypted'] or 'token' in row['setting_key'] or 'key' in row['setting_key']:
                if value and len(value) > 4:
                    value = value[:4] + '*' * (len(value) - 4)
            
            settings.append({
                'key': row['setting_key'],
                'value': value,
                'description': row['description'],
                'is_encrypted': row['is_encrypted']
            })
        
        return {
            'status': 'success',
            'category': category,
            'settings': settings
        }
        
    except Exception as e:
        logger.error(f"Error fetching settings for category {category}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/raw/{setting_key}")
async def get_raw_setting(setting_key: str):
    """
    Get raw setting value (for internal use)
    WARNING: Returns unmasked value
    """
    try:
        ch = get_clickhouse_client()
        
        query = """
        SELECT setting_value
        FROM AncientReport.settings
        FINAL
        WHERE setting_key = %(key)s
        LIMIT 1
        """
        
        result = ch.query(query, {'key': setting_key})
        
        if not result:
            raise HTTPException(status_code=404, detail="Setting not found")
        
        return {
            'status': 'success',
            'key': setting_key,
            'value': result[0]['setting_value']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching setting {setting_key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings")
async def update_settings(payload: SettingsUpdate):
    """
    Update multiple settings at once
    
    Example:
    {
        "settings": {
            "telegram_bot_token": "123456:ABC...",
            "telegram_chat_id": "123456789",
            "gemini_api_key": "AIza..."
        }
    }
    """
    try:
        ch = get_clickhouse_client()
        
        updated_count = 0
        errors = []
        
        for key, value in payload.settings.items():
            try:
                # Check if setting exists
                check_query = """
                SELECT setting_key, category, is_encrypted
                FROM AncientReport.settings
                FINAL
                WHERE setting_key = %(key)s
                LIMIT 1
                """
                
                existing = ch.query(check_query, {'key': key})
                
                if not existing:
                    logger.warning(f"Setting {key} does not exist, skipping")
                    errors.append(f"Setting '{key}' not found")
                    continue
                
                category = existing[0]['category']
                is_encrypted = existing[0]['is_encrypted']
                
                # Update setting (INSERT will trigger ReplacingMergeTree)
                update_query = """
                INSERT INTO AncientReport.settings 
                (setting_key, setting_value, category, description, is_encrypted, updated_at, updated_by)
                VALUES
                """
                
                # Get description
                desc_query = """
                SELECT description 
                FROM AncientReport.settings 
                FINAL 
                WHERE setting_key = %(key)s 
                LIMIT 1
                """
                desc_result = ch.query(desc_query, {'key': key})
                description = desc_result[0]['description'] if desc_result else ''
                
                values = f"('{key}', '{value}', '{category}', '{description}', {is_encrypted}, now(), 'api')"
                
                ch.execute(update_query + values)
                updated_count += 1
                
                logger.info(f"✅ Updated setting: {key} in category {category}")
                
            except Exception as e:
                error_msg = f"Failed to update {key}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Reload Telegram notifier if telegram settings changed
        telegram_keys = ['telegram_bot_token', 'telegram_chat_id', 'telegram_enabled']
        if any(key in payload.settings for key in telegram_keys):
            try:
                from alerts.telegram_notifier import get_telegram_notifier
                # Force reload
                import sys
                if 'src.alerts.telegram_notifier' in sys.modules:
                    del sys.modules['src.alerts.telegram_notifier']
                logger.info("🔄 Reloaded Telegram notifier with new settings")
            except Exception as e:
                logger.warning(f"Could not reload Telegram notifier: {e}")
        
        return {
            'status': 'success' if updated_count > 0 else 'partial',
            'updated': updated_count,
            'errors': errors if errors else None,
            'message': f'Updated {updated_count} settings'
        }
        
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/test-telegram")
async def test_telegram():
    """Test Telegram configuration by sending a test message"""
    try:
        from alerts.telegram_notifier import send_telegram_alert
        
        test_alert = {
            'level': 'info',
            'title': 'Settings Test',
            'message': 'Telegram integration is configured correctly! ✅',
            'server': 'settings-ui',
            'hostname': 'settings-ui'
        }
        
        result = await send_telegram_alert(test_alert)
        
        if result:
            return {
                'status': 'success',
                'message': 'Test message sent successfully! Check your Telegram.'
            }
        else:
            return {
                'status': 'error',
                'message': 'Failed to send test message. Check your bot token and chat ID.'
            }
            
    except Exception as e:
        logger.error(f"Error testing Telegram: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/settings/{setting_key}")
async def reset_setting(setting_key: str):
    """Reset a setting to empty value"""
    try:
        ch = get_clickhouse_client()
        
        # Check if exists
        check_query = """
        SELECT setting_key, category, description, is_encrypted
        FROM AncientReport.settings
        FINAL
        WHERE setting_key = %(key)s
        LIMIT 1
        """
        
        existing = ch.query(check_query, {'key': setting_key})
        
        if not existing:
            raise HTTPException(status_code=404, detail="Setting not found")
        
        row = existing[0]
        
        # Insert empty value
        reset_query = f"""
        INSERT INTO AncientReport.settings 
        (setting_key, setting_value, category, description, is_encrypted, updated_at, updated_by)
        VALUES ('{setting_key}', '', '{row['category']}', '{row['description']}', {row['is_encrypted']}, now(), 'api')
        """
        
        ch.execute(reset_query)
        
        logger.info(f"Reset setting: {setting_key}")
        
        return {
            'status': 'success',
            'message': f'Setting {setting_key} reset to empty'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting setting {setting_key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

