import logging
import pandas as pd
from datetime import datetime, timedelta
from config.settings import (
    WORK_START, WORK_END, MAX_DAILY_HOURS, HOLIDAYS,
    LUNCH_START, LUNCH_END, BREAK_1_START, BREAK_1_END, BREAK_2_START, BREAK_2_END, DINNER_START, DINNER_END
)

def calculate_working_hours_with_holidays(start_time, end_time):
    if pd.isna(start_time) or pd.isna(end_time):
        logging.warning(f"⛔ NaT 발생: 시작={start_time}, 완료={end_time}")
        return 0

    total_hours = 0
    current_time = start_time

    while current_time < end_time:
        current_day = current_time.date()
        is_weekend = current_day.weekday() == 6  # 일요일만 제외
        is_holiday = current_day in HOLIDAYS

        if is_holiday:
            logging.info(f"🚫 공휴일 제외: {current_day}")
            current_time = datetime.combine(current_day + timedelta(days=1), WORK_START)
            continue

        work_start = datetime.combine(current_day, WORK_START)
        work_end = datetime.combine(current_day, WORK_END)

        # 주말은 9시간 제한
        max_daily_hours = 9 if is_weekend else MAX_DAILY_HOURS

        # 실제 근무한 구간 계산
        work_start = max(work_start, current_time)
        work_end = min(work_end, end_time)

        daily_hours = (work_end - work_start).total_seconds() / 3600

        # 휴게 시간 차감
        breaks = [(LUNCH_START, LUNCH_END), (BREAK_1_START, BREAK_1_END),
                  (BREAK_2_START, BREAK_2_END), (DINNER_START, DINNER_END)]
        for b_start, b_end in breaks:
            b_start_dt = datetime.combine(current_day, b_start)
            b_end_dt = datetime.combine(current_day, b_end)
            if work_start < b_end_dt and b_start_dt < work_end:
                overlap = (min(work_end, b_end_dt) - max(work_start, b_start_dt)).total_seconds() / 3600
                daily_hours -= overlap
                logging.debug(f"☕ 휴게시간 차감 {b_start}-{b_end} → {overlap:.2f}시간")

        daily_hours = min(daily_hours, max_daily_hours)
        logging.info(f"✅ {current_day} 근무시간: {daily_hours:.2f}시간")

        total_hours += daily_hours
        current_time = datetime.combine(current_day + timedelta(days=1), WORK_START)

    logging.info(f"🧮 최종 소요시간: {total_hours:.2f}시간 (시작={start_time}, 완료={end_time})")
    return total_hours
