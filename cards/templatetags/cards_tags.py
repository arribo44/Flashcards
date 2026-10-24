# cards/templatetags/cards_tags.py

from django import template
from django.db.models import Count, Q
from django.utils import timezone

from cards.models import BOXES

register = template.Library()


def box_counts(deck):
    """Return the number of cards and of due cards in each box of a deck."""
    counts = {
        row["box"]: row
        for row in deck.cards.values("box").annotate(
            card_count=Count("id"),
            due_count=Count("id", filter=Q(due_date__lte=timezone.localdate())),
        ).order_by()
    }
    return [
        {
            "number": box_num,
            "card_count": counts.get(box_num, {}).get("card_count", 0),
            "due_count": counts.get(box_num, {}).get("due_count", 0),
        }
        for box_num in BOXES
    ]


@register.inclusion_tag("cards/box_links.html", takes_context=True)
def boxes_as_links(context, deck):
    return {
        "deck": deck,
        "boxes": box_counts(deck),
        "request": context.get("request"),
    }


@register.inclusion_tag("cards/sidebar.html", takes_context=True)
def sidebar(context):
    """The sidebar menu: main pages, then the user's decks (the current one unfolded)."""
    request = context["request"]
    current = context.get("deck")
    decks = request.user.decks.annotate(
        due_count=Count("cards", filter=Q(cards__due_date__lte=timezone.localdate()))
    )
    return {
        "request": request,
        "url_name": request.resolver_match.url_name if request.resolver_match else "",
        "decks": decks,
        "current_deck": current if getattr(current, "pk", None) else None,
    }
