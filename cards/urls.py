# cards/urls.py

from django.urls import path

from . import views

urlpatterns = [
    path(
        "",
        views.DeckListView.as_view(),
        name="deck-list"
    ),
    path(
        "stats",
        views.StatsView.as_view(),
        name="stats"
    ),
    path(
        "decks/new",
        views.DeckCreateView.as_view(),
        name="deck-create"
    ),
    path(
        "decks/<int:pk>/edit",
        views.DeckUpdateView.as_view(),
        name="deck-update"
    ),
    path(
        "decks/<int:pk>/delete",
        views.DeckDeleteView.as_view(),
        name="deck-delete"
    ),
    path(
        "decks/<int:deck_pk>/",
        views.CardListView.as_view(),
        name="card-list"
    ),
    path(
        "decks/<int:deck_pk>/new",
        views.CardCreateView.as_view(),
        name="card-create"
    ),
    path(
        "decks/<int:deck_pk>/edit/<int:pk>",
        views.CardUpdateView.as_view(),
        name="card-update"
    ),
    path(
        "decks/<int:deck_pk>/delete/<int:pk>",
        views.CardDeleteView.as_view(),
        name="card-delete"
    ),
    path(
        "decks/<int:deck_pk>/import",
        views.CardImportView.as_view(),
        name="card-import"
    ),
    path(
        "decks/<int:deck_pk>/anki",
        views.AnkiUploadView.as_view(),
        name="anki-upload"
    ),
    path(
        "decks/<int:deck_pk>/anki/fields",
        views.AnkiMapView.as_view(),
        name="anki-map"
    ),
    path(
        "decks/<int:deck_pk>/study",
        views.StudyView.as_view(),
        name="study"
    ),
    path(
        "decks/<int:deck_pk>/box/<int:box_num>",
        views.BoxView.as_view(),
        name="box"
    ),
]
