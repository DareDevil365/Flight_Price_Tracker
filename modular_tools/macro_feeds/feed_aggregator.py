"""
Modular Tools — Macro Feeds
Generalized, reusable aggregator for yfinance (market data), feedparser (RSS news),
and holidays (regional public holidays). Not specific to flights.
"""

import sys
import asyncio
import aiohttp
from loguru import logger
from datetime import datetime

# Lazy/Safe imports
YFINANCE_AVAILABLE = False
FEEDPARSER_AVAILABLE = False
HOLIDAYS_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    logger.warning("yfinance not installed. Please run: pip install yfinance")

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    logger.warning("feedparser not installed. Please run: pip install feedparser")

try:
    import holidays
    HOLIDAYS_AVAILABLE = True
except ImportError:
    logger.warning("holidays not installed. Please run: pip install holidays")


class MacroFeedAggregator:
    def __init__(self):
        pass

    def get_ticker_history(self, symbol: str, period: str = "30d") -> dict:
        """
        Fetches historical data for a Yahoo Finance ticker.
        E.g. symbol="BZ=F" (Brent Crude), symbol="USDINR=X" (USD/INR exchange rate).
        No API keys required.
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance is unavailable. Returning empty history.")
            return {"symbol": symbol, "current_price": None, "change_pct": 0.0}

        try:
            ticker = yf.Ticker(symbol)
            # Fetch history synchronously (wrap in run_in_executor for async if needed)
            hist = ticker.history(period=period)
            
            if hist.empty:
                logger.warning(f"Ticker history returned empty dataframe for {symbol}")
                return {"symbol": symbol, "current_price": None, "change_pct": 0.0}

            current = float(hist["Close"].iloc[-1])
            initial = float(hist["Close"].iloc[0])
            change_pct = ((current - initial) / initial) * 100.0 if initial else 0.0
            
            # Format history list
            history_list = []
            for dt, row in hist.iterrows():
                history_list.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "price": float(row["Close"])
                })

            return {
                "symbol": symbol,
                "current_price": round(current, 2),
                "change_pct": round(change_pct, 2),
                "history": history_list
            }
        except Exception as e:
            logger.error(f"Failed to fetch yfinance data for {symbol}: {e}")
            return {"symbol": symbol, "current_price": None, "change_pct": 0.0}

    def get_rss_news(self, rss_urls: list[str], keywords: list[str] = None, max_results: int = 10) -> list[dict]:
        """
        Fetches and parses RSS feeds, optionally filtering entries by keyword matches.
        No API keys required.
        """
        if not FEEDPARSER_AVAILABLE:
            logger.warning("feedparser is unavailable. Returning empty news.")
            return []

        articles = []
        keywords_lower = [k.lower() for k in keywords] if keywords else None

        for url in rss_urls:
            try:
                feed = feedparser.parse(url)
                if feed.bozo:
                    logger.debug(f"RSS Feed parsed with warning/error (bozo) for URL: {url}")

                for entry in feed.entries:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    link = entry.get("link", "")
                    published = entry.get("published", "")

                    # Combine title and summary for keyword searching
                    full_text = (title + " " + summary).lower()

                    if keywords_lower:
                        # Match if any keyword is present
                        if not any(k in full_text for k in keywords_lower):
                            continue

                    articles.append({
                        "title": title,
                        "summary": summary[:300], # truncate summary
                        "link": link,
                        "published": published
                    })

                    if len(articles) >= max_results:
                        break
            except Exception as e:
                logger.warning(f"Failed to parse RSS feed {url}: {e}")
                continue

            if len(articles) >= max_results:
                break

        return articles[:max_results]

    def get_public_holidays(self, country: str = "India", years: list[int] = None) -> dict:
        """
        Fetches national holiday dates using the python-holidays package.
        No API keys required.
        """
        if not HOLIDAYS_AVAILABLE:
            logger.warning("holidays package is unavailable. Returning empty calendar.")
            return {}

        if not years:
            years = [datetime.now().year]

        holiday_calendar = {}
        try:
            # Dynamically instantiate country class
            # E.g. country="India", resolves to holidays.India
            country_class = getattr(holidays, country)
            h_obj = country_class(years=years)
            
            for date_obj, name in h_obj.items():
                date_str = date_obj.strftime("%Y-%m-%d")
                holiday_calendar[date_str] = name
        except AttributeError:
            logger.error(f"Holidays class for country '{country}' not found.")
        except Exception as e:
            logger.error(f"Failed to fetch holidays for {country}: {e}")

        return holiday_calendar

    async def fetch_webpage_content(self, url: str, headers: dict = None, timeout: int = 5) -> str:
        """Fetches raw webpage HTML asynchronously using aiohttp with custom headers."""
        if not headers:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"HTTP fetch failed for {url} with status {response.status}")
        except Exception as e:
            logger.warning(f"Exception during web fetch for {url}: {e}")
        return ""
