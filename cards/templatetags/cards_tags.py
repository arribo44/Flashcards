# cards/templatetags/cards_tags.py

from django import template
from django.db.models import Count, Q
from django.utils import timezone

from cards.models import BOXES

register = template.Library()

@register.inclusion_tag("cards/box_links.html")
def boxes_as_links(deck):
    counts = {
        row["box"]: row
        for row in deck.cards.values("box").annotate(
            card_count=Count("id"),
            due_count=Count("id", filter=Q(due_date__lte=timezone.localdate())),
        ).order_by()
    }
    boxes = [
        {
            "number": box_num,
            "card_count": counts.get(box_num, {}).get("card_count", 0),
            "due_count": counts.get(box_num, {}).get("due_count", 0),
        }
        for box_num in BOXES
    ]

    return {"deck": deck, "boxes": boxes}
