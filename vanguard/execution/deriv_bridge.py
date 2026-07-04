import asyncio
import json
import requests
import websockets
from datetime import datetime
from typing import Optional
from data.models import SignalResult, TradeRecord
from config import (
    DERIV_API_BASE,
    DERIV_API_TOKEN,
    DERIV_APP_ID,
    STAKE_USD,
    TRADE_DURATION,
    DEMO_MODE,
)
from utils.logger import get_logger

log = get_logger(__name__)


class DerivBridge:
    """
    Handles authenticated WebSocket connection to Deriv.
    Places binary contracts and listens for results.
    """

    def __init__(self):
        self.ws              = None
        self.connected       = False
        self.pending_trades: dict = {}
        self._next_req_id    = 1
        self._pending_requests = {}
        self._result_queue   = asyncio.Queue()
        self._reader_task    = None

    async def connect(self):
        log.info("Connecting to Deriv...")
        headers = {
            "Authorization": f"Bearer {DERIV_API_TOKEN}",
            "Deriv-App-ID": DERIV_APP_ID,
            "Content-Type": "application/json",
        }
        accounts_response = requests.get(
            f"{DERIV_API_BASE}/trading/v1/options/accounts",
            headers=headers,
            timeout=15,
        )
        accounts_response.raise_for_status()
        accounts = accounts_response.json().get("data", [])
        target_type = "demo" if DEMO_MODE else "real"
        account = next(
            (item for item in accounts if item.get("account_type") == target_type),
            None,
        )
        if not account:
            raise ConnectionError(f"No Deriv {target_type} account is available")

        otp_response = requests.post(
            (
                f"{DERIV_API_BASE}/trading/v1/options/accounts/"
                f"{account['account_id']}/otp"
            ),
            headers=headers,
            timeout=15,
        )
        otp_response.raise_for_status()
        ws_url = otp_response.json().get("data", {}).get("url")
        if not ws_url:
            raise ConnectionError("Deriv OTP response did not include a WebSocket URL")

        self.ws = await websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
        )
        self.connected = True
        self._reader_task = asyncio.create_task(self._reader_loop())
        log.info(f"Authenticated - {target_type.upper()} mode")

    async def _reader_loop(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                req_id = data.get("req_id")
                future = self._pending_requests.pop(req_id, None)
                if future and not future.done():
                    future.set_result(data)

                contract_data = data.get("proposal_open_contract")
                if not contract_data:
                    continue
                contract_id = contract_data.get("contract_id")
                record = self.pending_trades.get(contract_id)
                if not record or not contract_data.get("is_sold"):
                    continue

                profit = float(contract_data.get("profit", 0))
                record.profit = profit
                record.result = (
                    "WIN" if profit > 0 else "TIE" if profit == 0 else "LOSS"
                )
                del self.pending_trades[contract_id]
                await self._result_queue.put(record)
        except Exception as exc:
            if self.connected:
                log.error(f"Deriv WebSocket reader failed: {exc}")
        finally:
            self.connected = False
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(ConnectionError("Deriv WebSocket closed"))
            self._pending_requests.clear()

    async def _request(self, payload):
        if not self.connected or not self.ws:
            raise ConnectionError("Deriv WebSocket is not connected")

        req_id = self._next_req_id
        self._next_req_id += 1
        payload = dict(payload, req_id=req_id)
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = future
        await self.ws.send(json.dumps(payload))
        return await asyncio.wait_for(future, timeout=20)

    async def _validate_duration(self, symbol, contract_type):
        response = await self._request({"contracts_for": symbol})
        if response.get("error"):
            raise ValueError(response["error"].get("message", "Contract lookup failed"))

        duration_minutes = TRADE_DURATION // 60
        required = f"{duration_minutes}m"
        available = response.get("contracts_for", {}).get("available", [])
        matching = [
            item for item in available
            if item.get("contract_type") == contract_type
        ]
        if any(item.get("min_contract_duration") == required for item in matching):
            return duration_minutes

        minimums = sorted({
            item.get("min_contract_duration")
            for item in matching
            if item.get("min_contract_duration")
        })
        raise ValueError(
            f"{symbol} {contract_type} does not support {required}; "
            f"available minimum durations: {', '.join(minimums) or 'unknown'}"
        )

    async def place_trade(self, signal: SignalResult) -> Optional[TradeRecord]:
        """
        Places a 5-minute binary contract based on VANGUARD signal.
        Returns TradeRecord with contract_id.
        """
        if not self.connected or signal.direction is None:
            return None

        contract_type = "CALL" if signal.direction == "UP" else "PUT"
        try:
            duration_minutes = await self._validate_duration(
                signal.asset,
                contract_type,
            )
        except ValueError as exc:
            log.error(f"Trade blocked: {exc}")
            return None

        proposal_msg = {
            "proposal": 1,
            "amount": STAKE_USD,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "duration": duration_minutes,
            "duration_unit": "m",
            "underlying_symbol": signal.asset,
        }

        log.info(
            f"🔥 Requesting {signal.direction} | "
            f"${STAKE_USD} | {TRADE_DURATION}s | {signal.asset}"
        )

        proposal_resp = await self._request(proposal_msg)

        if proposal_resp.get("error"):
            log.error(f"Proposal failed: {proposal_resp['error']}")
            return None

        proposal_id = proposal_resp.get("proposal", {}).get("id")
        if not proposal_id:
            log.error("No proposal ID received")
            return None

        buy_msg = {
            "buy": proposal_id,
            "price": STAKE_USD
        }

        buy_resp = await self._request(buy_msg)

        if buy_resp.get("error"):
            log.error(f"Buy failed: {buy_resp['error']}")
            return None

        contract_id = buy_resp.get("buy", {}).get("contract_id")
        buy_price = buy_resp.get("buy", {}).get("buy_price")

        record = TradeRecord(
            id              = None,
            timestamp       = datetime.utcnow(),
            asset           = signal.asset,
            direction       = signal.direction,
            stake           = STAKE_USD,
            duration        = TRADE_DURATION,
            signal          = signal,
            broker_trade_id = contract_id,
            result          = None,
            profit          = None,
            demo            = DEMO_MODE
        )

        if contract_id:
            self.pending_trades[contract_id] = record
            log.info(f"Trade placed — ID: {contract_id}")
        else:
            log.error(f"Trade placement failed: {buy_resp}")
            return None

        return record

    async def listen_results(self):
        """
        Listens for trade close events and updates pending trade records.
        Run this as a background task alongside the signal engine.
        """
        await self._request({
            "proposal_open_contract": 1,
            "subscribe": 1
        })
        while self.connected:
            yield await self._result_queue.get()

    async def close(self):
        self.connected = False
        if self._reader_task:
            self._reader_task.cancel()
        if self.ws:
            await self.ws.close()
