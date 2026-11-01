"""
telegram_bot.py - Simple Telegram alerter using the Bot API.
Configure via .env:
    TELEGRAM_BOT_TOKEN=<your token>
    TELEGRAM_CHAT_ID=<your chat id>

Get a token: BotFather (@BotFather on Telegram)
Get your chat ID: @userinfobot or send a message to your bot then check
    https://api.telegram.org/bot<TOKEN>/getUpdates
"""
import logging
import os
import urllib.request
import urllib.parse
import json
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramAlerter:
    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.token   = token   or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID",   "")
        self._enabled = bool(self.token and self.chat_id)

        if not self._enabled:
            logger.info(
                "Telegram alerter disabled — set TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_CHAT_ID in .env to enable alerts."
            )

    def send_alert(self, message: str) -> bool:
        """Send a Markdown-formatted message to the configured Telegram chat."""
        if not self._enabled:
            return False
        try:
            url  = self.BASE_URL.format(token=self.token)
            data = urllib.parse.urlencode({
                "chat_id":    self.chat_id,
                "text":       message,
                "parse_mode": "Markdown",
            }).encode()
            req  = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    logger.info("Telegram alert sent successfully")
                    return True
                logger.warning("Telegram API error: %s", result)
        except Exception as exc:
            logger.error("Failed to send Telegram alert: %s", exc)
        return False

    def send_daily_summary(self, stats: dict) -> bool:
        """Send a daily summary report."""
        if not self._enabled:
            return False
        msg = (
            "📊 *Daily Air Quality Summary*\n"
            f"Date: {stats.get('date', 'N/A')}\n\n"
            f"PM2.5 — Avg: `{stats.get('pm2p5_avg', 'N/A')} µg/m³`  "
            f"Max: `{stats.get('pm2p5_max', 'N/A')} µg/m³`\n"
            f"PM10  — Avg: `{stats.get('pm10p0_avg', 'N/A')} µg/m³`  "
            f"Max: `{stats.get('pm10p0_max', 'N/A')} µg/m³`\n"
            f"Readings: `{stats.get('count', 0)}`"
        )
        return self.send_alert(msg)

