from datetime import datetime, timedelta, time, date
import pandas as pd
from config.settings import (
    WORK_START, WORK_END, MAX_DAILY_HOURS,
    LUNCH_START, LUNCH_END,
    DINNER_START, DINNER_END,
    BREAK_1_START, BREAK_1_END,
    BREAK_2_START, BREAK_2_END,
    HOLIDAYS
)

def calculate_working_hours_with_holidays(start_time, end_time):
    if pd.isna(start_time) or pd.isna(end_time):
        return 0

    total_hours = 0
    current_time = start_time

    while current_time < end_time:
        current_day = current_time.date()
        if current_day in HOLIDAYS:
            current_time = datetime.combine(current_day + timedelta(days=1), WORK_START)
            continue
#	•	>= 5 → 토요일, 일요일 포함
#	•	== 5 → 토요일만 포함 (일요일 제외)
        is_weekend = current_day.weekday() >= 5
        work_start = datetime.combine(current_day, WORK_START)
        work_end = datetime.combine(current_day, time(17, 0) if is_weekend else WORK_END)

        actual_start = max(current_time, work_start)
        actual_end = min(end_time, work_end)

        if actual_start >= actual_end:
            current_time = datetime.combine(current_day + timedelta(days=1), WORK_START)
            continue

        work_seconds = (actual_end - actual_start).total_seconds()

        for b_start, b_end in [
            (LUNCH_START, LUNCH_END),
            (BREAK_1_START, BREAK_1_END),
            (BREAK_2_START, BREAK_2_END),
            (DINNER_START, DINNER_END)
        ]:
            break_start = datetime.combine(current_day, b_start)
            break_end = datetime.combine(current_day, b_end)
            if actual_start < break_end and break_start < actual_end:
                overlap = (min(actual_end, break_end) - max(actual_start, break_start)).total_seconds()
                work_seconds -= max(0, overlap)

        daily_limit = 9 if is_weekend else MAX_DAILY_HOURS
        total_hours += min(work_seconds / 3600, daily_limit)

        current_time = datetime.combine(current_day + timedelta(days=1), WORK_START)

    return total_hours


