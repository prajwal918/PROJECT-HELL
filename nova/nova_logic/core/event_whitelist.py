import requests
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Optional
import json

EASTERN = pytz.timezone("America/New_York")

class NewsEvent:
    def __init__(self, timestamp: datetime, currency: str, name: str, impact: str, actual: Optional[str] = None, forecast: Optional[str] = None, previous: Optional[str] = None):
        self.timestamp = timestamp.astimezone(EASTERN)
        self.currency = currency
        self.name = name
        self.impact = impact
        self.actual = actual
        self.forecast = forecast
        self.previous = previous

    def is_high_impact(self) -> bool:
        return self.impact in ["High", "3", "High Impact"]

    def is_within_minutes(self, minutes: int) -> bool:
        now = datetime.now(EASTERN)
        delta = abs((self.timestamp - now).total_seconds())
        return delta <= minutes * 60

class NewsCalendarAPI:
    """
    Fetches economic calendar data from multiple sources
    Used for Gate 1: Event Whitelist
    """

    def __init__(self):
        self.fred_api_key = "FRED_API_KEY"
        self.tradingeconomics_api_key = "TRADING_ECONOMICS_KEY"
        self.events_cache = []
        self.last_fetch = None
        self.cache_ttl = timedelta(minutes=5)

    def _is_cache_valid(self) -> bool:
        if self.last_fetch is None:
            return False
        return datetime.now() - self.last_fetch < self.cache_ttl

    def fetch_ff_calendar(self, days: int = 1) -> List[NewsEvent]:
        """
        Fetches Factory Orders, FOMC minutes from FRED
        Requires FRED API key
        """
        events = []
        try:
            url = f"https://api.stlouisfed.org/fred/releases/dates?api_key={self.fred_api_key}&file_type=json"
            response = requests.get(url, timeout=10)
            data = response.json()

            now = datetime.now(EASTERN)
            cutoff = now + timedelta(days=days)

            for release in data.get("release_dates", []):
                release_date = datetime.strptime(release["release_date"], "%Y-%m-%d")
                release_date = EASTERN.localize(release_date)

                if release_date <= cutoff:
                    name = release["release_name"]
                    if any(keyword in name.lower() for keyword in ["fomc", "factory", "orders", "durable"]):
                        events.append(NewsEvent(
                            timestamp=release_date,
                            currency="USD",
                            name=name,
                            impact="High" if "fomc" in name.lower() else "Medium"
                        ))

            return events
        except Exception as e:
            print(f"[Calendar] FRED fetch error: {e}")
            return []

    def fetch_tradingeconomics_calendar(self, days: int = 1) -> List[NewsEvent]:
        """
        Fetches comprehensive economic calendar from Trading Economics
        """
        events = []
        try:
            url = f"https://api.tradingeconomics.com/calendar?c={self.tradingeconomics_api_key}&f=json"
            response = requests.get(url, timeout=15)
            data = response.json()

            now = datetime.now(EASTERN)
            cutoff = now + timedelta(days=days)

            for item in data:
                try:
                    event_date = datetime.strptime(item["Date"], "%Y-%m-%dT%H:%M:%S")
                    event_date = pytz.utc.localize(event_date).astimezone(EASTERN)

                    if event_date <= cutoff:
                        impact_map = {"Low": "Low", "1": "Low", "Medium": "Medium", "2": "Medium", "High": "High", "3": "High"}
                        impact = impact_map.get(item["Importance"], "Low")

                        currency = item["Country"][:3].upper() if item["Country"] else "USD"

                        events.append(NewsEvent(
                            timestamp=event_date,
                            currency=currency,
                            name=item["Event"],
                            impact=impact,
                            actual=item.get("Actual"),
                            forecast=item.get("Forecast"),
                            previous=item.get("Previous")
                        ))
                except (ValueError, KeyError):
                    continue

            return events
        except Exception as e:
            print(f"[Calendar] Trading Economics fetch error: {e}")
            return []

    def fetch_investing_calendar(self) -> List[NewsEvent]:
        """
        Scrapes Investing.com economic calendar (fallback)
        """
        events = []
        try:
            url = "https://www.investing.com/economic-calendar/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=15)
            print(f"[Calendar] Investing.com returned {len(response.text)} bytes")
            return events
        except Exception as e:
            print(f"[Calendar] Investing.com scrape error: {e}")
            return []

    def fetch_all_events(self, force_refresh: bool = False) -> List[NewsEvent]:
        """
        Fetches events from all sources, merges and deduplicates
        """
        if self._is_cache_valid() and not force_refresh:
            return self.events_cache

        print("[Calendar] Fetching events from all sources...")

        events = []
        events.extend(self.fetch_ff_calendar())
        events.extend(self.fetch_tradingeconomics_calendar())
        if not events:
            events.extend(self.fetch_investing_calendar())

        events.sort(key=lambda e: e.timestamp)
        self.events_cache = events
        self.last_fetch = datetime.now()

        print(f"[Calendar] Fetched {len(events)} events")
        return events

    def get_upcoming_events(self, minutes_ahead: int = 30) -> List[NewsEvent]:
        """
        Returns high-impact events within next N minutes
        Used for pre-news monitoring window
        """
        events = self.fetch_all_events()
        upcoming = [e for e in events if e.is_high_impact() and e.is_within_minutes(minutes_ahead)]
        upcoming.sort(key=lambda e: e.timestamp)
        return upcoming

    def get_recent_events(self, minutes_back: int = 5) -> List[NewsEvent]:
        """
        Returns high-impact events that occurred in last N minutes
        Used for post-news anchor detection
        """
        events = self.fetch_all_events()
        now = datetime.now(EASTERN)
        cutoff = now - timedelta(minutes=minutes_back)

        recent = [e for e in events if e.is_high_impact() and e.timestamp >= cutoff]
        recent.sort(key=lambda e: e.timestamp, reverse=True)
        return recent

class EventWhitelist:
    """
    Gate 1: Event Whitelist
    Filters news events based on predefined whitelist
    """

    WHITELIST = [
        "FOMC Statement",
        "FOMC Minutes",
        "Fed Interest Rate Decision",
        "Non-Farm Payrolls",
        "Unemployment Rate",
        "CPI (MoM)",
        "CPI (YoY)",
        "Core CPI",
        "Retail Sales (MoM)",
        "Retail Sales (YoY)",
        "GDP (QoQ)",
        "GDP (YoY)",
        "PMI",
        "Services PMI",
        "Manufacturing PMI",
        "ADP Non-Farm Employment Change",
        "Consumer Confidence",
        "Existing Home Sales",
        "New Home Sales",
        "Durable Goods Orders",
        "Factory Orders (MoM)",
        "ECB Interest Rate Decision",
        "ECB Press Conference",
        "BOE Interest Rate Decision",
        "BOE MPC Minutes",
        "BOJ Interest Rate Decision",
        "BOJ Policy Statement",
        "RBA Interest Rate Decision",
        "RBA Governor Statement",
        "SNB Interest Rate Decision",
        "BOC Interest Rate Decision",
        "BOC Monetary Policy Report",
    ]

    TARGET_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]

    def __init__(self):
        self.calendar = NewsCalendarAPI()

    def is_whitelisted(self, event: NewsEvent) -> bool:
        """
        Checks if event is in whitelist AND targets relevant currency
        """
        name_match = any(keyword in event.name for keyword in self.WHITELIST)
        currency_match = event.currency in self.TARGET_CURRENCIES

        return name_match and currency_match

    def get_tradeable_events(self, minutes_ahead: int = 30) -> List[NewsEvent]:
        """
        Returns upcoming events that pass Gate 1 (whitelist filter)
        """
        upcoming = self.calendar.get_upcoming_events(minutes_ahead)
        tradeable = [e for e in upcoming if self.is_whitelisted(e)]

        print(f"[Whitelist] {len(upcoming)} high-impact events, {len(tradeable)} pass whitelist")
        return tradeable

    def get_score(self, event: NewsEvent) -> int:
        """
        Returns Gate 1 score (0 or 25 points)
        """
        return 25 if self.is_whitelisted(event) else 0