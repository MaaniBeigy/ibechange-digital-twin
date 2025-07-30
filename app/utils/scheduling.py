import os
import random
from datetime import datetime, timedelta
from typing import List

from dotenv import load_dotenv

load_dotenv()


def generate_random_schedule(
    start_time: datetime, end_time: datetime
) -> List[datetime]:
    min_notifications_per_day = int(os.getenv("MIN_NOTIFICATIONS_PER_DAY", 1))
    max_notifications_per_day = int(os.getenv("MAX_NOTIFICATIONS_PER_DAY", 5))
    min_notifications_per_week = int(os.getenv("MIN_NOTIFICATIONS_PER_WEEK", 5))
    max_notifications_per_week = int(os.getenv("MAX_NOTIFICATIONS_PER_WEEK", 20))
    cooldown_minutes = int(os.getenv("BETWEEN_NOTIFICATION_COOLDOWN", 180))
    start_hour = datetime.strptime(os.getenv("START_HOUR", "08:00"), "%H:%M").time()
    end_hour = datetime.strptime(os.getenv("END_HOUR", "22:00"), "%H:%M").time()

    schedules = []
    current_date = start_time.date()
    end_date = end_time.date()
    days = (end_date - current_date).days + 1

    total_notifications = random.randint(
        min_notifications_per_week, max_notifications_per_week
    )
    notifications_per_day = total_notifications // days
    notifications_per_day = max(
        min_notifications_per_day, min(notifications_per_day, max_notifications_per_day)
    )

    candidate_times = []

    while current_date <= end_date:
        daily_candidates = []
        attempts = 0
        while len(daily_candidates) < notifications_per_day and attempts < 100:
            hour = random.randint(start_hour.hour, end_hour.hour - 1)
            minute = random.randint(0, 59)
            scheduled_time = datetime.combine(
                current_date, datetime.min.time()
            ) + timedelta(hours=hour, minutes=minute)

            if not (start_time <= scheduled_time <= end_time):
                attempts += 1
                continue

            too_close = any(
                abs((scheduled_time - existing).total_seconds()) < cooldown_minutes * 60
                for existing in schedules
            )
            if not too_close:
                daily_candidates.append(scheduled_time)
                schedules.append(scheduled_time)
            attempts += 1

        current_date += timedelta(days=1)

    schedules.sort()
    return schedules[:total_notifications]
