import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date as _date
import logging

log = logging.getLogger("azalyst.macro")

class ForexFactoryFetcher:
    """Fetches and parses the Forex Factory calendar XML feed."""

    XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    def __init__(self):
        self.events = []

    def fetch_events(self):
        """Fetches upcoming High/Medium-impact macro events for this week.

        Past events are filtered out: scoring already-released events as
        "upcoming macro tailwind" was double-counting tape that the price
        engine has already digested. We filter conservatively — if a date
        string fails to parse we keep the event rather than silently drop it.
        """
        try:
            req = urllib.request.Request(
                self.XML_URL,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            self.events = []
            today = _date.today()
            dropped_past = 0

            for event in root.findall('event'):
                title = event.find('title').text if event.find('title') is not None else ""
                country = event.find('country').text if event.find('country') is not None else ""
                date_str = event.find('date').text if event.find('date') is not None else ""
                time_str = event.find('time').text if event.find('time') is not None else ""
                impact = event.find('impact').text if event.find('impact') is not None else ""

                if impact not in ("High", "Medium"):
                    continue

                # Drop past-dated events. Forex Factory date format is MM-DD-YYYY.
                # Conservative: if parsing fails, keep the event.
                if date_str:
                    try:
                        ev_date = datetime.strptime(date_str, "%m-%d-%Y").date()
                        if ev_date < today:
                            dropped_past += 1
                            continue
                    except (ValueError, TypeError):
                        pass

                self.events.append({
                    "title": title,
                    "country": country,
                    "impact": impact,
                    "date": date_str,
                    "time": time_str
                })

            log.info(
                "Fetched %d High/Medium upcoming macro events (dropped %d past).",
                len(self.events), dropped_past,
            )
            return self.events

        except Exception as e:
            log.warning(f"Failed to fetch Forex Factory macro events: {e}")
            return []
