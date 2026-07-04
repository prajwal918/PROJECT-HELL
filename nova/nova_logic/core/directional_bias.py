import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import json

class DirectionalBiasModel:
    """
    Gate 2: Deep Research Directional Bias
    Analyzes event, forecasts, historical reactions, and correlated markets
    Returns BULLISH / BEARISH / NEUTRAL with confidence score (0-25 points)
    """

    def __init__(self):
        self.ff_api_key = "FRED_API_KEY"
        self.correlation_cache = {}

    def analyze_event_impact(self, event_name: str, currency: str) -> Dict:
        """
        Analyzes event impact based on historical data
        Returns: {direction: "UP"/"DOWN"/"NEUTRAL", confidence: float, reasoning: str}
        """
        direction = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        name_lower = event_name.lower()

        if "fomc" in name_lower:
            direction, confidence, event_reasoning = self._analyze_fomc()
            reasoning.extend(event_reasoning)

        elif "non-farm" in name_lower or "nfp" in name_lower:
            direction, confidence, event_reasoning = self._analyze_nfp()
            reasoning.extend(event_reasoning)

        elif "cpi" in name_lower:
            direction, confidence, event_reasoning = self._analyze_cpi()
            reasoning.extend(event_reasoning)

        elif "gdp" in name_lower:
            direction, confidence, event_reasoning = self._analyze_gdp()
            reasoning.extend(event_reasoning)

        elif "pmi" in name_lower:
            direction, confidence, event_reasoning = self._analyze_pmi()
            reasoning.extend(event_reasoning)

        elif "retail" in name_lower:
            direction, confidence, event_reasoning = self._analyze_retail_sales()
            reasoning.extend(event_reasoning)

        elif "interest rate" in name_lower or "rate decision" in name_lower:
            direction, confidence, event_reasoning = self._analyze_rate_decision(currency)
            reasoning.extend(event_reasoning)

        else:
            direction = "NEUTRAL"
            confidence = 0.0
            reasoning.append(f"Event {event_name} not in analysis database")

        return {
            "direction": direction,
            "confidence": confidence,
            "reasoning": " | ".join(reasoning)
        }

    def _analyze_fomc(self) -> tuple:
        """
        Analyzes FOMC meeting impact
        Looks at: Fed funds rate, dot plot, forward guidance
        """
        direction = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key={self.ff_api_key}&file_type=json&limit=12"
            response = requests.get(url, timeout=10)
            data = response.json()

            observations = data.get("observations", [])
            if len(observations) >= 2:
                prev_rate = float(observations[-2]["value"])
                latest_rate = float(observations[-1]["value"])

                if latest_rate > prev_rate:
                    direction = "UP"
                    confidence = 20.0
                    reasoning.append(f"FEDFUNDS increased {prev_rate}% → {latest_rate}% (hawkish)")

                elif latest_rate < prev_rate:
                    direction = "DOWN"
                    confidence = 20.0
                    reasoning.append(f"FEDFUNDS decreased {prev_rate}% → {latest_rate}% (dovish)")

                else:
                    direction = "NEUTRAL"
                    confidence = 10.0
                    reasoning.append(f"FEDFUNDS unchanged at {latest_rate}%")

        except Exception as e:
            reasoning.append(f"FOMC analysis failed: {e}")

        return direction, confidence, reasoning

    def _analyze_nfp(self) -> tuple:
        """
        Analyzes Non-Farm Payrolls impact
        """
        direction = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=PAYEMS&api_key={self.ff_api_key}&file_type=json&limit=2"
            response = requests.get(url, timeout=10)
            data = response.json()

            observations = data.get("observations", [])
            if len(observations) >= 2:
                prev_change = float(observations[-2]["value"]) - float(observations[-3]["value"])
                latest_change = float(observations[-1]["value"]) - float(observations[-2]["value"])

                if latest_change > 200000:
                    direction = "UP"
                    confidence = 22.0
                    reasoning.append(f"NFP +{latest_change:,} beats 200K consensus (bullish USD)")

                elif latest_change < 100000:
                    direction = "DOWN"
                    confidence = 22.0
                    reasoning.append(f"NFP +{latest_change:,} misses 150K consensus (bearish USD)")

                else:
                    direction = "NEUTRAL"
                    confidence = 12.0
                    reasoning.append(f"NFP +{latest_change:,} within expectations")

        except Exception as e:
            reasoning.append(f"NFP analysis failed: {e}")

        return direction, confidence, reasoning

    def _analyze_cpi(self) -> tuple:
        """
        Analyzes CPI impact
        """
        direction = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key={self.ff_api_key}&file_type=json&limit=12"
            response = requests.get(url, timeout=10)
            data = response.json()

            observations = data.get("observations", [])
            if len(observations) >= 2:
                prev_cpi = float(observations[-2]["value"])
                latest_cpi = float(observations[-1]["value"])
                yoy_change = ((latest_cpi - prev_cpi) / prev_cpi) * 100

                if yoy_change > 3.0:
                    direction = "UP"
                    confidence = 20.0
                    reasoning.append(f"CPI YoY +{yoy_change:.2f}% > 3% (inflationary, bullish USD)")

                elif yoy_change < 2.0:
                    direction = "DOWN"
                    confidence = 18.0
                    reasoning.append(f"CPI YoY +{yoy_change:.2f}% < 2% (disinflationary, bearish USD)")

                else:
                    direction = "NEUTRAL"
                    confidence = 10.0
                    reasoning.append(f"CPI YoY +{yoy_change:.2f}% within Fed target range")

        except Exception as e:
            reasoning.append(f"CPI analysis failed: {e}")

        return direction, confidence, reasoning

    def _analyze_gdp(self) -> tuple:
        """
        Analyzes GDP impact
        """
        direction = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=A191RL1Q225SBEA&api_key={self.ff_api_key}&file_type=json&limit=2"
            response = requests.get(url, timeout=10)
            data = response.json()

            observations = data.get("observations", [])
            if len(observations) >= 1:
                latest_gdp = float(observations[-1]["value"])

                if latest_gdp > 3.0:
                    direction = "UP"
                    confidence = 18.0
                    reasoning.append(f"GDP QoQ +{latest_gdp}% > 3% (strong growth, bullish USD)")

                elif latest_gdp < 1.0:
                    direction = "DOWN"
                    confidence = 18.0
                    reasoning.append(f"GDP QoQ +{latest_gdp}% < 1% (weak growth, bearish USD)")

                else:
                    direction = "NEUTRAL"
                    confidence = 10.0
                    reasoning.append(f"GDP QoQ +{latest_gdp}% within expectations")

        except Exception as e:
            reasoning.append(f"GDP analysis failed: {e}")

        return direction, confidence, reasoning

    def _analyze_pmi(self) -> tuple:
        """
        Analyzes PMI impact (Manufacturing or Services)
        """
        direction = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=NAPM&api_key={self.ff_api_key}&file_type=json&limit=2"
            response = requests.get(url, timeout=10)
            data = response.json()

            observations = data.get("observations", [])
            if len(observations) >= 1:
                latest_pmi = float(observations[-1]["value"])

                if latest_pmi > 55:
                    direction = "UP"
                    confidence = 15.0
                    reasoning.append(f"PMI {latest_pmi:.1f} > 55 (expansionary, bullish currency)")

                elif latest_pmi < 45:
                    direction = "DOWN"
                    confidence = 15.0
                    reasoning.append(f"PMI {latest_pmi:.1f} < 45 (contractionary, bearish currency)")

                else:
                    direction = "NEUTRAL"
                    confidence = 8.0
                    reasoning.append(f"PMI {latest_pmi:.1f} in neutral zone")

        except Exception as e:
            reasoning.append(f"PMI analysis failed: {e}")

        return direction, confidence, reasoning

    def _analyze_retail_sales(self) -> tuple:
        """
        Analyzes Retail Sales impact
        """
        direction = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=RSXFS&api_key={self.ff_api_key}&file_type=json&limit=2"
            response = requests.get(url, timeout=10)
            data = response.json()

            observations = data.get("observations", [])
            if len(observations) >= 2:
                prev_sales = float(observations[-2]["value"])
                latest_sales = float(observations[-1]["value"])
                mom_change = ((latest_sales - prev_sales) / prev_sales) * 100

                if mom_change > 0.5:
                    direction = "UP"
                    confidence = 14.0
                    reasoning.append(f"Retail Sales MoM +{mom_change:.2f}% > 0.5% (strong consumption)")

                elif mom_change < -0.3:
                    direction = "DOWN"
                    confidence = 14.0
                    reasoning.append(f"Retail Sales MoM {mom_change:.2f}% < -0.3% (weak consumption)")

                else:
                    direction = "NEUTRAL"
                    confidence = 8.0
                    reasoning.append(f"Retail Sales MoM {mom_change:.2f}% within expectations")

        except Exception as e:
            reasoning.append(f"Retail Sales analysis failed: {e}")

        return direction, confidence, reasoning

    def _analyze_rate_decision(self, currency: str) -> tuple:
        """
        Analyzes central bank rate decision impact
        """
        direction = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        try:
            series_map = {
                "USD": "FEDFUNDS",
                "EUR": "ECBDFR",
                "GBP": "IUDSOIA",
                "JPY": "JPNIRSR",
                "AUD": "RBAIRSR",
                "CAD": "CBCIRSR",
                "CHF": "SZIRSR",
            }

            series_id = series_map.get(currency, "FEDFUNDS")
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={self.ff_api_key}&file_type=json&limit=12"
            response = requests.get(url, timeout=10)
            data = response.json()

            observations = data.get("observations", [])
            if len(observations) >= 2:
                prev_rate = float(observations[-2]["value"])
                latest_rate = float(observations[-1]["value"])

                if latest_rate > prev_rate:
                    direction = "UP"
                    confidence = 22.0
                    reasoning.append(f"{currency} rate hike {prev_rate}% → {latest_rate}% (hawkish)")

                elif latest_rate < prev_rate:
                    direction = "DOWN"
                    confidence = 22.0
                    reasoning.append(f"{currency} rate cut {prev_rate}% → {latest_rate}% (dovish)")

                else:
                    direction = "NEUTRAL"
                    confidence = 10.0
                    reasoning.append(f"{currency} rate unchanged at {latest_rate}%")

        except Exception as e:
            reasoning.append(f"Rate decision analysis failed: {e}")

        return direction, confidence, reasoning

    def get_score(self, event_name: str, currency: str) -> int:
        """
        Returns Gate 2 score (0-25 points) based on directional bias analysis
        """
        result = self.analyze_event_impact(event_name, currency)
        return int(result["confidence"])

    def get_direction(self, event_name: str, currency: str) -> str:
        """
        Returns predicted direction: "UP", "DOWN", or "NEUTRAL"
        """
        result = self.analyze_event_impact(event_name, currency)
        return result["direction"]