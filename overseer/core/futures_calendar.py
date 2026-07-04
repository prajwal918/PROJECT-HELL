#!/usr/bin/env python3
"""
Futures Rollover Calendar — CME quarterly contract roll.

CME FX futures roll quarterly: March, June, September, December.
Third Wednesday of the expiry month.

In the last 10 days before expiry:
- Volume migrates to next contract
- Spreads widen
- DOM depth collapses
- Gate signals degrade (reading a thinning market)

This module prevents the system from trading degraded signals.
"""

import calendar
import logging
import os
from datetime import date, timedelta
from typing import Dict, Optional

LOGGER = logging.getLogger("overseer.futures_calendar")

QUARTERLY_MONTHS = {3, 6, 9, 12}

PRE_ROLL_DAYS = int(os.getenv("FUTURES_PRE_ROLL_DAYS", "14"))
NEAR_EXPIRY_DAYS = int(os.getenv("FUTURES_NEAR_EXPIRY_DAYS", "7"))
ROLL_NOW_DAYS = int(os.getenv("FUTURES_ROLL_NOW_DAYS", "3"))

_SYMBOL_SUFFIX_MAP = {}
for _m in QUARTERLY_MONTHS:
    _SYMBOL_SUFFIX_MAP[f"M{_m}"] = _m
    _SYMBOL_SUFFIX_MAP[f"U{_m}" if _m == 9 else f""] = _m


def _get_next_expiry(today: date) -> date:
    """Third Wednesday of the next quarterly month."""
    month = today.month
    year = today.year

    for m in sorted(QUARTERLY_MONTHS):
        if m > month or (m == month and today.day < 15):
            target_month, target_year = m, year
            break
    else:
        target_month, target_year = 3, year + 1

    cal = calendar.monthcalendar(target_year, target_month)
    wednesdays = [week[2] for week in cal if week[2] != 0]
    third_wednesday = wednesdays[2]

    return date(target_year, target_month, third_wednesday)


def _get_expiry_for_contract(symbol: str, today: date) -> Optional[date]:
    """
    Derive expiry from the contract code embedded in the symbol.
    E.g. 6EM6 -> June 2026, 6EU6 -> September 2026.
    If no code found, fall back to next quarterly expiry.
    """
    month_codes = {
        "H": 3,
        "M": 6,
        "U": 9,
        "Z": 12,
    }

    if len(symbol) >= 2:
        code = symbol[-2]
        year_digit = symbol[-1]

        if code in month_codes:
            target_month = month_codes[code]
            try:
                target_year = 2020 + int(year_digit)
                if target_year < today.year:
                    target_year += 10
            except ValueError:
                pass
            else:
                cal = calendar.monthcalendar(target_year, target_month)
                wednesdays = [week[2] for week in cal if week[2] != 0]
                if wednesdays:
                    return date(target_year, target_month, wednesdays[2])

    return _get_next_expiry(today)


def get_roll_status(symbol: str, today: Optional[date] = None) -> Dict:
    """
    Returns roll status for a CME futures contract.

    status: ACTIVE | PRE_ROLL | NEAR_EXPIRY | ROLL_NOW
    signal_quality_multiplier: 1.0 | 0.85 | 0.6 | 0.3
    should_trade: True | False (False only for ROLL_NOW)
    """
    today = today or date.today()

    expiry = _get_expiry_for_contract(symbol, today)
    if expiry is None:
        expiry = _get_next_expiry(today)

    days_to_expiry = (expiry - today).days

    if days_to_expiry <= ROLL_NOW_DAYS:
        status = "ROLL_NOW"
        quality_mult = 0.3
        should_trade = False
    elif days_to_expiry <= NEAR_EXPIRY_DAYS:
        status = "NEAR_EXPIRY"
        quality_mult = 0.6
        should_trade = True
    elif days_to_expiry <= PRE_ROLL_DAYS:
        status = "PRE_ROLL"
        quality_mult = 0.85
        should_trade = True
    else:
        status = "ACTIVE"
        quality_mult = 1.0
        should_trade = True

    next_expiry_str = expiry.isoformat()

    return {
        "status": status,
        "days_to_expiry": days_to_expiry,
        "next_expiry": next_expiry_str,
        "signal_quality_multiplier": quality_mult,
        "should_trade": should_trade,
    }


def get_all_roll_statuses(symbols: list, today: Optional[date] = None) -> Dict[str, Dict]:
    """Get roll status for all tracked symbols."""
    today = today or date.today()
    return {s: get_roll_status(s, today) for s in symbols}
