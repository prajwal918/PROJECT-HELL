import asyncio
import json
import requests
import websockets
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from config import (
    DERIV_API_BASE,
    DERIV_API_TOKEN,
    DERIV_APP_ID,
    STAKE_USD,
    TRADE_DURATION,
    USE_DEMO_MODE,
    ASSET,
)

@dataclass
class TradeRecord:
    id: Optional[int]
    timestamp: datetime
    asset: str
    direction: str
    stake: float
    duration: int
    broker_trade_id: Optional[str]
    result: Optional[str]
    profit: Optional[float]
    demo: bool

class DerivExecution:
    """
    Automated binary options execution via Deriv API
    Handles authentication, trade placement, and result tracking
    """

    def __init__(self):
        self.ws = None
        self.connected = False
        self.pending_trades: dict = {}
        self._next_req_id = 1
        self._pending_requests = {}
        self._result_queue = asyncio.Queue()
        self._reader_task = None

    async def connect(self):
        """Connects to Deriv WebSocket with authentication"""
        print("[AEGIS] Connecting to Deriv...")
        headers = {
            "Authorization": f"Bearer {DERIV_API_TOKEN}",
            "Deriv-App-ID": DERIV_APP_ID,
            "Content-Type": "application/json",
        }

        try:
            accounts_response = requests.get(
                f"{DERIV_API_BASE}/trading/v1/options/accounts",
                headers=headers,
                timeout=15,
            )
            accounts_response.raise_for_status()
            accounts = accounts_response.json().get("data", [])

            target_type = "demo" if USE_DEMO_MODE else "real"
            account = next(
                (item for item in accounts if item.get("account_type") == target_type),
                None,
            )

            if not account:
                raise ConnectionError(f"No Deriv {target_type} account available")

            otp_response = requests.post(
                f"{DERIV_API_BASE}/trading/v1/options/accounts/{account['account_id']}/otp",
                headers=headers,
                timeout=15,
            )
            otp_response.raise_for_status()
            ws_url = otp_response.json().get("data", {}).get("url")

            if not ws_url:
                raise ConnectionError("Deriv OTP response did not include WebSocket URL")

            self.ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=10,
            )
            self.connected = True
            self._reader_task = asyncio.create_task(self._reader_loop())
            print(f"[AEGIS] Connected to Deriv - {target_type.upper()} mode")

        except Exception as e:
            raise ConnectionError(f"Deriv connection failed: {e}")

    async def _reader_loop(self):
        """WebSocket message reader loop"""
        try:
            async for message in self.ws:
                data = json.loads(message)
                req_id = data.get("req_id")

                if req_id:
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
                print(f"[AEGIS] Deriv WebSocket reader error: {exc}")
        finally:
            self.connected = False
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(ConnectionError("Deriv WebSocket closed"))
            self._pending_requests.clear()

    async def _request(self, payload):
        """Sends request and waits for response"""
        if not self.connected or not self.ws:
            raise ConnectionError("Deriv WebSocket is not connected")

        req_id = self._next_req_id
        self._next_req_id += 1
        payload = dict(payload, req_id=req_id)
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = future
        await self.ws.send(json.dumps(payload))
        return await asyncio.wait_for(future, timeout=20)

    async def place_trade(self, direction: str) -> Optional[TradeRecord]:
        """
        Places 15-minute binary trade
        direction: "CALL" (up) or "PUT" (down)
        """
        if not self.connected or direction not in ["CALL", "PUT"]:
            return None

        try:
            duration_minutes = TRADE_DURATION // 60
            required = f"{duration_minutes}m"

            response = await self._request({"contracts_for": ASSET})
            if response.get("error"):
                raise ValueError(response["error"].get("message"))

            available = response.get("contracts_for", {}).get("available", [])
            matching = [item for item in available if item.get("contract_type") == direction]

            if not any(item.get("min_contract_duration") == required for item in matching):
                raise ValueError(f"{ASSET} does not support {required} duration")

            proposal_msg = {
                "proposal": 1,
                "amount": STAKE_USD,
                "basis": "stake",
                "contract_type": direction,
                "currency": "USD",
                "duration": duration_minutes,
                "duration_unit": "m",
                "underlying_symbol": ASSET,
            }

            print(f"[AEGIS] Placing {direction} | ${STAKE_USD} | {TRADE_DURATION}s | {ASSET}")

            proposal_resp = await self._request(proposal_msg)

            if proposal_resp.get("error"):
                print(f"[AEGIS] Proposal failed: {proposal_resp['error']}")
                return None

            proposal_id = proposal_resp.get("proposal", {}).get("id")
            if not proposal_id:
                print("[AEGIS] No proposal ID received")
                return None

            buy_msg = {"buy": proposal_id, "price": STAKE_USD}
            buy_resp = await self._request(buy_msg)

            if buy_resp.get("error"):
                print(f"[AEGIS] Buy failed: {buy_resp['error']}")
                return None

            contract_id = buy_resp.get("buy", {}).get("contract_id")

            record = TradeRecord(
                id=None,
                timestamp=datetime.utcnow(),
                asset=ASSET,
                direction=direction,
                stake=STAKE_USD,
                duration=TRADE_DURATION,
                broker_trade_id=contract_id,
                result=None,
                profit=None,
                demo=USE_DEMO_MODE,
            )

            if contract_id:
                self.pending_trades[contract_id] = record
                print(f"[AEGIS] Trade placed - ID: {contract_id}")

            return record

        except Exception as e:
            print(f"[AEGIS] Trade placement error: {e}")
            return None

    async def listen_results(self):
        """Yields completed trade results"""
        await self._request({"proposal_open_contract": 1, "subscribe": 1})
        while self.connected:
            yield await self._result_queue.get()

    async def close(self):
        """Closes WebSocket connection"""
        self.connected = False
        if self._reader_task:
            self._reader_task.cancel()
        if self.ws:
            await self.ws.close()
        print("[AEGIS] Disconnected from Deriv")