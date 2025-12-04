# ⚙️ Settings UI - Quick Start Guide

## Overview

Your dashboard now has a **Settings button** (⚙️ gear icon) in the top-right header, next to the alert bell.

## Features

### 📱 Telegram Configuration
- **Bot Token**: Your Telegram bot API token
- **Chat ID**: Your Telegram chat/group ID  
- **Enable/Disable**: Toggle Telegram notifications

### 🤖 AI Configuration
- **Gemini API Key**: Google Gemini API key
- **Model Name**: Which Gemini model to use (default: gemini-2.0-flash-exp)

### 🔔 Alert Configuration
- **Cooldown Minutes**: Prevent alert spam (default: 30 minutes)
- **Max History**: How many alerts to keep (default: 100)

## How to Use

### 1. Open Settings

Click the **⚙️ Settings icon** in the top-right corner of the dashboard (next to the bell icon).

### 2. Configure Telegram

1. **Get Bot Token** (see TELEGRAM_SETUP_GUIDE.md):
   - Message @BotFather on Telegram
   - Send `/newbot` and follow prompts
   - Copy the token

2. **Get Chat ID**:
   - Send message to your bot
   - Visit: `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
   - Copy the chat ID from JSON response

3. **Enter in Settings**:
   - Paste Bot Token
   - Paste Chat ID
   - Set "telegram_enabled" to "true"

4. **Test Connection**:
   - Click "Test" button next to Telegram section
   - Check your Telegram for test message

### 3. Configure Gemini AI

1. **Get API Key**:
   - Visit: https://makersuite.google.com/app/apikey
   - Create new API key
   - Copy the key

2. **Enter in Settings**:
   - Paste API Key
   - Optionally change model name

### 4. Save Settings

Click **"Save Settings"** button at the bottom of the modal.

## Features

✅ **Secure Storage**: Settings stored in ClickHouse database  
✅ **Password Masking**: Sensitive fields show/hide toggle (eye icon)  
✅ **Test Function**: Test Telegram before saving  
✅ **Real-time Updates**: Changes apply immediately  
✅ **Success/Error Messages**: Clear feedback on actions  
✅ **Beautiful UI**: Professional glassmorphism design  

## API Endpoints

The settings system exposes these endpoints:

- `GET /api/settings` - Get all settings (masked)
- `GET /api/settings/{category}` - Get settings by category
- `POST /api/settings` - Update settings
- `POST /api/settings/test-telegram` - Test Telegram configuration
- `DELETE /api/settings/{key}` - Reset a setting

## Database

Settings are stored in ClickHouse:

```sql
SELECT * FROM AncientReport.settings FINAL;
```

## Security

- **Sensitive fields** are masked in API responses (show only first 4 chars)
- **Show/Hide toggle** for passwords in UI
- **No plaintext logging** of sensitive values
- **Database-backed** configuration (not hardcoded)

## Troubleshooting

### Settings not saving

Check analysis service logs:
```bash
docker logs AncientReport-analysis | grep settings
```

### Telegram test fails

1. Verify bot token is correct
2. Ensure you've messaged the bot first
3. Check chat ID is correct (use getUpdates endpoint)
4. For groups, use negative ID (e.g., -123456789)

### Can't see settings button

1. Refresh browser (Ctrl+R or Cmd+R)
2. Clear browser cache
3. Check UI container is running:
   ```bash
   docker ps | grep ui
   ```

## Example Usage

### Via UI

1. Click ⚙️ Settings
2. Enter values
3. Click Save
4. Click Test (for Telegram)

### Via API

```bash
curl -X POST http://65.109.200.75:6800/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "telegram_bot_token": "123456:ABC...",
      "telegram_chat_id": "123456789",
      "telegram_enabled": "true",
      "gemini_api_key": "AIza..."
    }
  }'
```

### Test Telegram

```bash
curl -X POST http://65.109.200.75:6800/api/settings/test-telegram
```

## What's Next

After configuring:

1. **Telegram**: You'll receive alerts when thresholds are breached
2. **Gemini AI**: AI analysis will use your API key for insights
3. **Alerts**: System will monitor based on configured cooldown

## Default Alert Thresholds

- 🚨 Critical CPU: > 90%
- ⚠️ High CPU: > 80%
- 🚨 Critical Memory: > 90%
- ⚠️ High Memory: > 85%
- ⚠️ High Disk: > 90%
- ⚠️ Network Loss: > 100 packets

These can be customized in `analysis/src/alerts/alert_rules.py`.

## Support

- **Full Telegram Guide**: `/home/AncientReport/TELEGRAM_SETUP_GUIDE.md`
- **Logs**: `docker logs AncientReport-analysis`
- **Database**: `docker exec -it AncientReport-clickhouse clickhouse-client`


