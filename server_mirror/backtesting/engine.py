from datetime import datetime
import re

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

def parse_market_date_from_ticker(ticker: str) -> datetime | None:
    """
    Parses a ticker string (e.g., 'KXHIGHNY-26FEB05') into a datetime object.
    Returns None if the format doesn't match.
    """
    match = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", ticker)
    if not match:
        return None
    yy, mon_txt, dd = match.groups()
    month = _MONTHS.get(mon_txt)
    if not month:
        return None
    try:
        year = 2000 + int(yy)
        day = int(dd)
        return datetime(year, month, day)
    except ValueError:
        return None
