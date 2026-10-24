# cards/stats.py

from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate


def review_days(reviews):
    """Return the set of local dates on which at least one review happened."""
    return set(
        reviews.annotate(day=TruncDate("reviewed_at"))
        .values_list("day", flat=True)
        .distinct()
    )


def current_streak(days, today):
    """Count consecutive review days ending today, or yesterday if today is still open."""
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def longest_streak(days):
    best = 0
    for day in days:
        if day - timedelta(days=1) not in days:
            length = 1
            while day + timedelta(days=length) in days:
                length += 1
            best = max(best, length)
    return best


def daily_counts(reviews, today, num_days):
    """Return one {date, total, solved} entry per day, oldest first, zeros included."""
    start = today - timedelta(days=num_days - 1)
    rows = (
        reviews.filter(reviewed_at__date__gte=start)
        .annotate(day=TruncDate("reviewed_at"))
        .values("day")
        .annotate(total=Count("id"), solved=Count("id", filter=Q(solved=True)))
        .order_by()
    )
    by_day = {row["day"]: row for row in rows}
    return [
        {
            "date": day,
            "total": by_day.get(day, {}).get("total", 0),
            "solved": by_day.get(day, {}).get("solved", 0),
        }
        for day in (start + timedelta(days=offset) for offset in range(num_days))
    ]
