"""Telegram alerting integration for OVERSEER v12.

Sends formatted trade signals, system alerts, and status notifications
to a Telegram chat via the Bot API using ``aiohttp``.

Configuration (via ``.env``):
    TELEGRAM_BOT_TOKEN  – Bot API token from @BotFather
    TELEGRAM_CHAT_ID    – Target chat or channel ID

Features:
    • Async HTTP via aiohttp (non-blocking for the event loop)
    • Rate-limited to 30 messages / minute (Telegram enforced limit)
    • Graceful error handling — never crashes the main trading loop
    • Formatted trade alerts with gate states, TP levels, etc.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from typing import Any, Optional

LOGGER = logging.getLogger("overseer.telegram")

# ── constants ──
_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"
_RATE_LIMIT_WINDOW = 60.0  # seconds
_RATE_LIMIT_MAX = 30  # messages per window
_REQUEST_TIMEOUT_S = 10


class TelegramAlerter:
    """Async Telegram alerter for OVERSEER v12.

    Parameters
    ----------
    bot_token : str | None
        Override for the Telegram bot token (reads from env by default).
    chat_id : str | None
        Override for the Telegram chat ID (reads from env by default).
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        self._token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._enabled = bool(self._token and self._chat_id)

        # Rate-limiter: timestamps of recent sends
        self._send_timestamps: deque[float] = deque(maxlen=_RATE_LIMIT_MAX)

        # aiohttp session (created lazily)
        self._session: Any = None  # aiohttp.ClientSession

        if not self._enabled:
            LOGGER.warning(
                "Telegram alerts DISABLED — set TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_CHAT_ID in .env to enable.",
            )
        else:
            LOGGER.info("TelegramAlerter initialised — chat_id=%s", self._chat_id)

    # ── lifecycle ──

    async def _ensure_session(self) -> Any:
        """Lazily create the aiohttp session."""
        if self._session is None or self._session.closed:
            try:
                import aiohttp

                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S),
                )
            except ImportError:
                LOGGER.error(
                    "aiohttp not installed — run `pip install aiohttp` to enable Telegram alerts.",
                )
                self._enabled = False
                return None
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            LOGGER.debug("Telegram HTTP session closed.")

    # ── rate limiter ──

    def _can_send(self) -> bool:
        """Return True if we are within the rate limit."""
        now = time.monotonic()
        # Purge entries older than the window
        while self._send_timestamps and now - self._send_timestamps[0] > _RATE_LIMIT_WINDOW:
            self._send_timestamps.popleft()
        return len(self._send_timestamps) < _RATE_LIMIT_MAX

    def _record_send(self) -> None:
        self._send_timestamps.append(time.monotonic())

    # ── core send ──

    async def _post_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Low-level POST to Telegram sendMessage. Returns True on success."""
        if not self._enabled:
            return False

        if not self._can_send():
            LOGGER.warning("Rate limit reached — message dropped.")
            return False

        url = _TELEGRAM_API_BASE.format(token=self._token)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        # Retry logic for network resilience
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session = await self._ensure_session()
                if session is None: return False
                
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        self._record_send()
                        return True
                    elif resp.status == 429: # Too Many Requests
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        LOGGER.warning("Telegram 429: Rate limited. Retrying after %ds", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        body = await resp.text()
                        LOGGER.error("Telegram API %d: %s", resp.status, body[:200])
                        return False
            except (asyncio.TimeoutError, Exception) as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    LOGGER.warning("Telegram attempt %d failed: %s. Retrying in %ds...", attempt + 1, e, wait)
                    await asyncio.sleep(wait)
                    # Force recreate session on next attempt if it was a connection error
                    if self._session: await self.close()
                else:
                    LOGGER.error("Telegram failed after %d attempts: %s", max_retries, e)
        return False

    # ── public API ──

    async def send_alert(self, message: str) -> bool:
        """Send a plain text alert message.

        Parameters
        ----------
        message : str
            Human-readable text (HTML formatting supported).
        """
        return await self._post_message(message)

    async def send_trade_alert(self, signal: dict[str, Any]) -> bool:
        """Send a richly formatted trade signal notification.

        Expected ``signal`` keys:
            symbol, direction, entry, sl, tp1, tp2,
            quality_score, gate_states (dict),
            risk_amount, lot_size,
            continuation_score (optional)
        """
        direction_emoji = "🟢" if signal.get("direction", "").upper() == "BUY" else "🔴"
        confidence = signal.get("confidence", "")
        confidence_bar = {"HIGH": "🔥🔥🔥", "MODERATE": "⚡⚡", "NO_TRADE": "❌"}.get(
            confidence, ""
        )

        # Gate states summary
        gates = signal.get("gate_states", {})
        if gates:
            passed = sum(1 for v in gates.values() if v)
            total = len(gates)
            gate_summary = f"{passed}/{total} gates passed"
        else:
            gate_summary = "N/A"

        lines = [
            f"<b>{direction_emoji} OVERSEER TRADE SIGNAL</b>",
            "",
            f"<b>Symbol:</b>    {signal.get('symbol', '?')}",
            f"<b>Direction:</b> {signal.get('direction', '?')}",
            f"<b>Entry:</b>     {signal.get('entry', '?')}",
            f"<b>SL:</b>        {signal.get('sl', '?')}",
            f"<b>TP1:</b>       {signal.get('tp1', '?')}",
            f"<b>TP2:</b>       {signal.get('tp2', '?')}",
            "",
            f"<b>Quality:</b>   {signal.get('quality_score', '?')}",
            f"<b>Gates:</b>     {gate_summary}",
            f"<b>Risk:</b>      ${signal.get('risk_amount', '?')}",
            f"<b>Lots:</b>      {signal.get('lot_size', '?')}",
        ]

        # Optional continuation score (post-news)
        cont_score = signal.get("continuation_score")
        if cont_score is not None:
            lines.append("")
            lines.append(f"<b>📰 Continuation:</b> {cont_score} {confidence_bar}")
            breakdown = signal.get("continuation_breakdown", {})
            if breakdown:
                bd_str = " | ".join(f"{k}={v}" for k, v in breakdown.items())
                lines.append(f"<code>{bd_str}</code>")

        text = "\n".join(lines)
        return await self._post_message(text)

    async def send_system_alert(self, message: str) -> bool:
        """Send a system-level alert (halt, resume, error, startup).

        Parameters
        ----------
        message : str
            System message content.
        """
        text = f"⚙️ <b>OVERSEER SYSTEM</b>\n\n{message}"
        return await self._post_message(text)

    async def send_partial_close_alert(
        self,
        ticket: int,
        stage: str,
        lots_closed: float,
        remaining: float,
        price: float,
    ) -> bool:
        """Send a notification for TP1/TP2 partial close events."""
        emoji = "🎯" if stage == "TP1" else "🏆"
        text = (
            f"{emoji} <b>{stage} HIT</b>\n\n"
            f"<b>Ticket:</b>   {ticket}\n"
            f"<b>Closed:</b>   {lots_closed:.2f} lots @ {price:.5f}\n"
            f"<b>Remaining:</b> {remaining:.2f} lots"
        )
        return await self._post_message(text)

    async def send_event_alert(
        self,
        event_name: str,
        currency: str,
        lean: str,
        score: int,
    ) -> bool:
        """Send a notification when a macro event lean is scored."""
        lean_emoji = {"BEAT": "📈", "MISS": "📉", "NEUTRAL": "➖"}.get(lean, "❓")
        text = (
            f"{lean_emoji} <b>Event Analysis</b>\n\n"
            f"<b>Event:</b>    {event_name}\n"
            f"<b>Currency:</b> {currency}\n"
            f"<b>Lean:</b>     {lean}\n"
            f"<b>Score:</b>    {score:+d}"
        )
        return await self._post_message(text)
