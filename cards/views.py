# cards/views.py

import random

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Min, Q
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from django.shortcuts import get_object_or_404, redirect

from django.views.generic import (
    ListView,
    CreateView,
    DeleteView,
    FormView,
    UpdateView,
)

from .models import Card, Deck
from .forms import CardCheckForm, CardImportForm


STUDY_DIRECTIONS = {
    "forward": "Question → Réponse",
    "reverse": "Réponse → Question",
    "mixed": "Mélangé",
}

ANSWER_MODES = {
    "reveal": "Révéler la réponse",
    "type": "Taper la réponse",
}


class SignUpView(CreateView):
    form_class = UserCreationForm
    template_name = "registration/signup.html"

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        return redirect("deck-list")


class DeckListView(LoginRequiredMixin, ListView):
    model = Deck

    def get_queryset(self):
        return self.request.user.decks.annotate(
            card_count=Count("cards"),
            due_count=Count(
                "cards", filter=Q(cards__due_date__lte=timezone.localdate())
            ),
        )


class DeckCreateView(SuccessMessageMixin, LoginRequiredMixin, CreateView):
    model = Deck
    fields = ["name", "language"]
    success_message = "Paquet « %(name)s » créé."

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("card-list", args=[self.object.pk])


class DeckUpdateView(SuccessMessageMixin, LoginRequiredMixin, UpdateView):
    model = Deck
    fields = ["name", "language"]
    success_url = reverse_lazy("deck-list")
    success_message = "Paquet « %(name)s » enregistré."

    def get_queryset(self):
        return self.request.user.decks.all()


class DeckDeleteView(SuccessMessageMixin, LoginRequiredMixin, DeleteView):
    model = Deck
    success_url = reverse_lazy("deck-list")

    def get_queryset(self):
        return self.request.user.decks.annotate(card_count=Count("cards"))

    def get_success_message(self, cleaned_data):
        return f"Paquet « {self.object.name} » supprimé."


class UserDeckMixin(LoginRequiredMixin):
    """Load the deck from the URL, restricted to the logged-in user's decks."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.deck = get_object_or_404(
                Deck, pk=kwargs["deck_pk"], owner=request.user
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["deck"] = self.deck
        return context


class CardListView(UserDeckMixin, ListView):
    model = Card

    def get_queryset(self):
        return self.deck.cards.order_by("box", "-date_created")


class CardCreateView(SuccessMessageMixin, UserDeckMixin, CreateView):
    model = Card
    fields = ["question", "answer", "example", "box"]
    success_message = "Carte « %(question)s » ajoutée."

    def form_valid(self, form):
        form.instance.deck = self.deck
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("card-create", args=[self.deck.pk])


class CardUpdateView(SuccessMessageMixin, UserDeckMixin, UpdateView):
    model = Card
    fields = ["question", "answer", "example", "box"]
    success_message = "Carte « %(question)s » enregistrée."

    def get_queryset(self):
        return self.deck.cards.all()

    def get_success_url(self):
        return reverse("card-list", args=[self.deck.pk])


class CardDeleteView(SuccessMessageMixin, UserDeckMixin, DeleteView):
    model = Card

    def get_queryset(self):
        return self.deck.cards.all()

    def get_success_url(self):
        return reverse("card-list", args=[self.deck.pk])

    def get_success_message(self, cleaned_data):
        return f"Carte « {self.object.question} » supprimée."


class CardImportView(UserDeckMixin, FormView):
    """Add cards to the deck from a CSV file, skipping questions it already has."""

    form_class = CardImportForm
    template_name = "cards/card_import.html"

    def form_valid(self, form):
        rows = form.cleaned_data["csv_file"]
        known_questions = set(self.deck.cards.values_list("question", flat=True))
        new_cards = []
        for question, answer, example in rows:
            if question not in known_questions:
                known_questions.add(question)
                new_cards.append(Card(
                    deck=self.deck, question=question, answer=answer, example=example
                ))
        Card.objects.bulk_create(new_cards)

        imported = len(new_cards)
        skipped = len(rows) - imported
        message = f"{imported} carte{'s' if imported > 1 else ''} importée{'s' if imported > 1 else ''}."
        if skipped:
            message += f" {skipped} ignorée{'s' if skipped > 1 else ''} (déjà présente{'s' if skipped > 1 else ''})."
        messages.success(self.request, message)
        return redirect("card-list", deck_pk=self.deck.pk)


class StudyView(UserDeckMixin, ListView):
    """Quiz the user on a random card that is due today."""

    model = Card
    template_name = "cards/study.html"
    form_class = CardCheckForm

    def get_cards(self):
        return self.deck.cards.all()

    def get_queryset(self):
        return self.get_cards().filter(due_date__lte=timezone.localdate())

    def get_study_option(self, name, choices):
        """Read an option from the query string, remembered in the session."""
        session_key = f"study_{name}"
        value = self.request.GET.get(name)
        if value in choices:
            self.request.session[session_key] = value
        return self.request.session.get(session_key, next(iter(choices)))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        direction = self.get_study_option("direction", STUDY_DIRECTIONS)
        context["direction"] = direction
        context["directions"] = STUDY_DIRECTIONS
        context["answer_mode"] = self.get_study_option("answer_mode", ANSWER_MODES)
        context["answer_modes"] = ANSWER_MODES
        if self.object_list:
            context["check_card"] = random.choice(self.object_list)
            context["reverse"] = direction == "reverse" or (
                direction == "mixed" and random.random() < 0.5
            )
        else:
            context["next_due"] = (
                self.get_cards()
                .filter(due_date__gt=timezone.localdate())
                .aggregate(Min("due_date"))["due_date__min"]
            )
        return context

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            card = get_object_or_404(self.deck.cards, id=form.cleaned_data["card_id"])
            card.move(form.cleaned_data["solved"])

        return redirect(request.path)


class BoxView(StudyView):
    template_name = "cards/box.html"

    def get_cards(self):
        return self.deck.cards.filter(box=self.kwargs["box_num"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["box_number"] = self.kwargs["box_num"]
        context["box_total"] = self.get_cards().count()
        return context
