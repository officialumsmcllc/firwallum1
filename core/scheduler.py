"""
OFFICIALUM1 — Bedtime & Curfew Scheduler Engine
Controls scheduled internet cut-off windows for child devices.
Supports:
- Overnight schedules spanning midnight (e.g. 22:00 -> 06:00)
- Day-of-week selection (0=Monday, 6=Sunday)
- Automatic status evaluation for DNS queries
"""

from datetime import datetime, time as dtime
from typing import Dict, Any, Optional

def is_time_in_range(start_str: str, end_str: str, check_time: dtime) -> bool:
    """
    Checks if check_time falls between start_str (HH:MM) and end_str (HH:MM).
    Correctly handles midnight crossover (e.g. 22:00 -> 06:00).
    """
    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start = dtime(sh, sm)
        end = dtime(eh, em)
    except Exception:
        return False

    if start <= end:
        # Normal daytime range (e.g. 14:00 to 18:00)
        return start <= check_time <= end
    else:
        # Overnight range spanning midnight (e.g. 22:00 to 06:00)
        return check_time >= start or check_time <= end

def is_curfew_active(schedule: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """
    Evaluates whether a specific bedtime schedule is currently active.
    """
    if not schedule.get("is_active", 1):
        return False

    if now is None:
        now = datetime.now()

    # Day of week check (Python: 0=Monday .. 6=Sunday)
    active_days_str = str(schedule.get("days", "0,1,2,3,4,5,6"))
    active_days = [int(d.strip()) for d in active_days_str.split(",") if d.strip().isdigit()]
    
    current_weekday = now.weekday()
    if current_weekday not in active_days:
        # Check for yesterday's overnight schedule that rolled past midnight
        yesterday_weekday = (current_weekday - 1) % 7
        if yesterday_weekday not in active_days:
            return False

    start_str = schedule.get("start_time", "22:00")
    end_str = schedule.get("end_time", "06:00")

    return is_time_in_range(start_str, end_str, now.time())
