"""
Alert/notification system for surebet opportunities.
Supports: WebSocket push, Email, Desktop notifications (future).
"""
import os
import asyncio
import json
from datetime import datetime
from typing import Set
from loguru import logger

from ..algorithms.surebet_detector import SurebetResult


class ConnectionManager:
    """
    Manages WebSocket connections for real-time alerts.
    Broadcasts surebet opportunities to all connected clients.
    """

    def __init__(self):
        self.active_connections: Set = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    async def disconnect(self, websocket) -> None:
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected WebSocket clients."""
        if not self.active_connections:
            return

        payload = json.dumps(message, ensure_ascii=False, default=str)
        dead_connections = set()

        for connection in self.active_connections.copy():
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                dead_connections.add(connection)

        # Clean up dead connections
        async with self._lock:
            self.active_connections -= dead_connections

    async def broadcast_opportunity(self, result: SurebetResult) -> None:
        """Broadcast a surebet opportunity to all clients."""
        message = {
            "type": "opportunity",
            "data": result.to_dict(),
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast(message)

    async def broadcast_status(self, status: dict) -> None:
        """Broadcast system status update."""
        message = {
            "type": "status",
            "data": status,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast(message)

    async def broadcast_odds_update(self, event_key: str, bookmaker: str) -> None:
        """Notify clients that odds were updated."""
        message = {
            "type": "odds_update",
            "event_key": event_key,
            "bookmaker": bookmaker,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast(message)


class EmailNotifier:
    """Send email alerts for surebet opportunities."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.alert_email = os.getenv("ALERT_EMAIL", "")
        self.enabled = bool(self.smtp_user and self.smtp_password and self.alert_email)

    async def send_alert(self, result: SurebetResult) -> bool:
        """Send email alert for a surebet opportunity."""
        if not self.enabled:
            return False

        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            subject = (
                f"🎯 {'SUREBET' if result.is_profitable else 'Near Surebet'} | "
                f"{result.home_team} vs {result.away_team} | "
                f"{result.profit_margin:+.2f}%"
            )

            body = self._build_email_body(result)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_user
            msg["To"] = self.alert_email
            msg.attach(MIMEText(body, "html"))

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
            )

            logger.info(f"Email alert sent for {result.event_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False

    def _build_email_body(self, result: SurebetResult) -> str:
        """Build HTML email body for opportunity alert."""
        legs_html = ""
        for leg in result.legs:
            legs_html += f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd">{leg.bookmaker}</td>
                <td style="padding:8px;border:1px solid #ddd">{leg.team}</td>
                <td style="padding:8px;border:1px solid #ddd">{leg.outcome}</td>
                <td style="padding:8px;border:1px solid #ddd;font-weight:bold">{leg.odds}</td>
                <td style="padding:8px;border:1px solid #ddd">{leg.stake_percent:.2f}%</td>
            </tr>"""

        color = "#27ae60" if result.is_profitable else "#f39c12"
        badge = "SUREBET" if result.is_profitable else "NEAR SUREBET"

        return f"""
        <html><body style="font-family:Arial,sans-serif;max-width:600px">
        <div style="background:{color};color:white;padding:15px;border-radius:8px">
            <h2 style="margin:0">🎯 {badge} DETECTADO</h2>
        </div>
        <div style="padding:15px;background:#f8f9fa;margin:10px 0;border-radius:8px">
            <p><strong>Evento:</strong> {result.home_team} vs {result.away_team}</p>
            <p><strong>Liga:</strong> {result.league}</p>
            <p><strong>Mercado:</strong> {result.market_type}</p>
            <p><strong>Margen:</strong> <span style="color:{color};font-size:1.3em">{result.profit_margin:+.4f}%</span></p>
            <p><strong>Detectado:</strong> {result.detected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
        <table style="width:100%;border-collapse:collapse;margin:10px 0">
            <tr style="background:#343a40;color:white">
                <th style="padding:8px">Casa</th>
                <th style="padding:8px">Equipo</th>
                <th style="padding:8px">Resultado</th>
                <th style="padding:8px">Cuota</th>
                <th style="padding:8px">% Apuesta</th>
            </tr>
            {legs_html}
        </table>
        <p style="color:#666;font-size:0.8em">
            Sistema Surebet - Alerta automática. Las cuotas pueden cambiar rápidamente.
        </p>
        </body></html>
        """


class TelegramNotifier:
    """
    Send Telegram alerts for surebet opportunities via Bot API.

    Setup:
      1. Create a bot via @BotFather → get TELEGRAM_BOT_TOKEN
      2. Send any message to your bot, then visit:
         https://api.telegram.org/bot<TOKEN>/getUpdates
         to find your TELEGRAM_CHAT_ID (the "id" inside "chat")
      3. Set both as environment variables.

    Env vars:
      TELEGRAM_BOT_TOKEN   — e.g. "7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      TELEGRAM_CHAT_ID     — e.g. "123456789" (your personal chat or a group id)
      TELEGRAM_NEAR_SUREBETS — "true" to also alert near-surebets (default: false)
    """

    API_BASE = "https://api.telegram.org/bot{token}/sendMessage"
    BM_EMOJI = {"Betcris": "🔴", "HDLinea": "🟢", "JuancitoSport": "🟡"}

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.alert_near = os.getenv("TELEGRAM_NEAR_SUREBETS", "false").lower() == "true"
        self.enabled = bool(self.token and self.chat_id)
        self.active = self.enabled  # Runtime toggle (on/off by user)

        if self.enabled:
            logger.info("Telegram notifier enabled.")
        else:
            logger.info(
                "Telegram notifier disabled — set TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_CHAT_ID to enable."
            )

    async def send_surebet(self, result: SurebetResult) -> bool:
        """Send a Telegram message for a confirmed surebet."""
        return await self._send(result, is_near=False)

    async def send_near_surebet(self, result: SurebetResult) -> bool:
        """Send a Telegram message for a near-surebet (only if enabled)."""
        if not self.alert_near:
            return False
        return await self._send(result, is_near=True)

    async def _send(self, result: SurebetResult, is_near: bool) -> bool:
        if not self.enabled or not self.active:
            return False
        try:
            import aiohttp
            text = self._format_message(result, is_near)
            url = self.API_BASE.format(token=self.token)
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info(f"Telegram alert sent: {result.event_key}")
                        return True
                    body = await resp.text()
                    logger.warning(f"Telegram API error {resp.status}: {body}")
                    return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def _format_message(self, result: SurebetResult, is_near: bool) -> str:
        header = "⚡ NEAR SUREBET" if is_near else "🎯 SUREBET DETECTADO"
        color_word = "Posible ganancia" if is_near else "Ganancia garantizada"
        margin_sign = "+" if result.profit_margin > 0 else ""

        legs_text = ""
        for leg in result.legs:
            emoji = self.BM_EMOJI.get(leg.bookmaker, "📌")
            legs_text += (
                f"\n{emoji} <b>{leg.bookmaker}</b>  →  {leg.outcome} "
                f"(<i>{leg.team}</i>)  @  <b>{leg.odds:.3f}</b>  "
                f"→  {leg.stake_percent:.1f}%"
            )

        time_str = result.detected_at.strftime("%H:%M:%S UTC")

        return (
            f"{header}\n\n"
            f"<b>{result.home_team} vs {result.away_team}</b>\n"
            f"🏆 {result.league}  ·  {result.sport_code}  ·  {result.market_type}\n\n"
            f"💰 Margen: <b>{margin_sign}{result.profit_margin:.4f}%</b>  ({color_word})\n"
            f"📊 Prob. implícita total: {result.total_implied_prob * 100:.3f}%\n\n"
            f"📌 <b>Cómo apostar:</b>{legs_text}\n\n"
            f"🕐 {time_str}"
        )

    async def send_test(self) -> bool:
        """Send a test message to verify the bot is configured correctly."""
        if not self.enabled:
            logger.warning("Telegram not configured — cannot send test message.")
            return False
        try:
            import aiohttp
            url = self.API_BASE.format(token=self.token)
            payload = {
                "chat_id": self.chat_id,
                "text": "✅ <b>Surebet Detector</b> — Bot conectado correctamente.\nRecibirás alertas aquí cuando se detecte una oportunidad.",
                "parse_mode": "HTML",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    ok = resp.status == 200
                    logger.info(f"Telegram test {'OK' if ok else 'FAILED'} (status {resp.status})")
                    return ok
        except Exception as e:
            logger.error(f"Telegram test failed: {e}")
            return False


# Global connection manager instance (singleton)
ws_manager = ConnectionManager()
email_notifier = EmailNotifier()
telegram_notifier = TelegramNotifier()
