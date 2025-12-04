# 📱 Telegram Alert Setup Guide

This guide will help you set up Telegram notifications for your AncientReport dashboard.

## Step 1: Create a Telegram Bot

1. **Open Telegram** and search for `@BotFather`
2. **Start a chat** with BotFather
3. **Send command**: `/newbot`
4. **Choose a name** for your bot (e.g., "AncientReport Alerts")
5. **Choose a username** for your bot (must end in 'bot', e.g., "ancientreport_alerts_bot")
6. **Save the token**: BotFather will give you a token like:
   ```
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

## Step 2: Get Your Chat ID

### Method 1: Using Your Bot
1. **Start a chat** with your new bot (search for the username you created)
2. **Send any message** to the bot (e.g., "hello")
3. **Visit this URL** in your browser (replace YOUR_BOT_TOKEN):
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
4. **Find your chat_id** in the JSON response:
   ```json
   {
     "ok": true,
     "result": [{
       "message": {
         "chat": {
           "id": 123456789,  <- This is your chat ID
           "first_name": "Your Name"
         }
       }
     }]
   }
   ```

### Method 2: Using @userinfobot
1. **Search for** `@userinfobot` on Telegram
2. **Start a chat** and send `/start`
3. **Copy your ID** from the response

### Method 3: Using a Group (for team notifications)
1. **Create a Telegram group**
2. **Add your bot** to the group (search by username)
3. **Make the bot an admin** (optional but recommended)
4. **Send a message** in the group
5. **Visit**: `https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates`
6. **Find the negative chat_id** (group IDs are negative numbers like -987654321)

## Step 3: Configure AncientReport

### On the Server (xcr9)

SSH into your server:
```bash
ssh root@65.109.200.75
cd /home/AncientReport
```

### Option A: Environment Variables (Recommended)

Edit the docker-compose file:
```bash
nano docker-compose.yml
```

Add these environment variables to the `analysis` service:
```yaml
analysis:
  environment:
    # ... existing variables ...
    TELEGRAM_BOT_TOKEN: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
    TELEGRAM_CHAT_ID: "123456789"  # or "-987654321" for groups
```

### Option B: Create .env file

Create a `.env` file:
```bash
nano .env
```

Add your credentials:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

Update docker-compose.yml to use the .env file:
```yaml
analysis:
  env_file:
    - .env
```

## Step 4: Restart Services

Restart the analysis container:
```bash
docker compose restart analysis
```

Check logs to verify Telegram is configured:
```bash
docker logs AncientReport-analysis | grep Telegram
```

You should see:
```
INFO Telegram notifications enabled for chat ID: 123456789
```

## Step 5: Test Your Setup

### Test Alert (Manual)

You can trigger a test alert by running this in the analysis container:
```bash
docker exec -it AncientReport-analysis python3 -c "
import asyncio
from src.alerts import send_telegram_alert

async def test():
    alert = {
        'level': 'info',
        'title': 'Test Alert',
        'message': 'Telegram integration is working!',
        'server': 'test',
    }
    result = await send_telegram_alert(alert)
    print(f'Alert sent: {result}')

asyncio.run(test())
"
```

### Monitor Real Alerts

Wait for actual system alerts. Default rules:
- 🚨 **Critical CPU**: > 90%
- ⚠️ **High CPU**: > 80%
- 🚨 **Critical Memory**: > 90%
- ⚠️ **High Memory**: > 85%
- ⚠️ **High Disk**: > 90%
- ⚠️ **Network Loss**: > 100 packets dropped

## Alert Message Format

You'll receive formatted messages like:

```
🚨 CRITICAL ALERT

High CPU Usage
CPU usage exceeded 90%

🖥️ Server: `xcr9`
📊 Metric: `cpu_usage_percent`
📈 Value: `95.5`
⚖️ Threshold: `90`

🕐 2025-12-04 01:23:45 UTC
```

## Customizing Alert Rules

Edit the alert rules in:
```
/home/AncientReport/analysis/src/alerts/alert_rules.py
```

Example custom rule:
```python
AlertRule(
    name='Custom Alert Name',
    metric='metric_name',
    condition='>',        # >, <, >=, <=, ==
    threshold=75.0,
    level='warning',      # critical, warning, info
    cooldown_minutes=30   # Prevent spam
)
```

## Features

✅ **Real-time notifications** - Get alerted instantly
✅ **Smart cooldown** - Prevents alert spam
✅ **Multiple levels** - Critical, Warning, Info
✅ **Rich formatting** - Markdown formatted messages
✅ **Group support** - Send to teams
✅ **Detailed info** - Server, metric, value, threshold
✅ **Dual alerts** - Browser notifications + Telegram

## Troubleshooting

### No alerts received

1. **Check bot token**:
   ```bash
   docker exec AncientReport-analysis env | grep TELEGRAM
   ```

2. **Verify bot is started**: Send a message to your bot

3. **Check logs**:
   ```bash
   docker logs -f AncientReport-analysis | grep -i telegram
   ```

4. **Test connection**:
   ```bash
   curl "https://api.telegram.org/botYOUR_TOKEN/getMe"
   ```

### Alerts not triggering

1. **Check if metrics exceed thresholds**
2. **Verify alert cooldown hasn't been triggered**
3. **Check analysis service logs**:
   ```bash
   docker logs AncientReport-analysis --tail 100
   ```

### Group notifications not working

1. **Ensure bot is a member** of the group
2. **Make bot an admin** (recommended)
3. **Use negative chat_id** for groups (e.g., -987654321)
4. **Send a message** after adding bot, then get updates

## Security Best Practices

1. **Keep your bot token secret** - Never commit to git
2. **Use environment variables** - Don't hardcode credentials
3. **Restrict bot permissions** - Only give necessary admin rights
4. **Rotate tokens periodically** - Use `/revoke` in BotFather
5. **Monitor bot usage** - Check for unauthorized access

## Support

If you need help:
- Check logs: `docker logs AncientReport-analysis`
- Verify Telegram API: https://core.telegram.org/bots/api
- Test bot connectivity: https://api.telegram.org/botYOUR_TOKEN/getMe


