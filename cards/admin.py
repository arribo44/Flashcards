from django.contrib import admin

from .models import Card, Deck, Review


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ["name", "language", "owner", "date_created"]
    list_filter = ["language", "owner"]
    search_fields = ["name"]


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["question", "answer", "box", "deck"]
    list_filter = ["box", "deck__language", "deck"]
    search_fields = ["question", "answer", "example"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["reviewed_at", "card", "deck", "solved"]
    list_filter = ["solved", "deck"]
    date_hierarchy = "reviewed_at"
