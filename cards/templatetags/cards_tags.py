# cards/templatetags/cards_tags.py

from django import template
from django.db.models import Count

from cards.models import BOXES

register = template.Library()

@register.inclusion_tag("cards/box_links.html")
def boxes_as_links(deck):
    counts = dict(
        deck.cards.values_list("box").annotate(Count("id")).order_by()
    )
    boxes = [
        {"number": box_num, "card_count": counts.get(box_num, 0)}
        for box_num in BOXES
    ]

    return {"deck": deck, "boxes": boxes}
