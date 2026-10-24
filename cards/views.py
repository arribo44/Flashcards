# cards/views.py

import random

from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Min, Q
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from django.shortcuts import get_object_or_404, redirect

from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
)

from .models import Card, Deck
from .forms import CardCheckForm


STUDY_DIRECTIONS = {
    "forward": "Question → Answer",
    "reverse": "Answer → Question",
    "mixed": "Mixed",
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


class DeckCreateView(LoginRequiredMixin, CreateView):
    model = Deck
    fields = ["name", "language"]

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("card-list", args=[self.object.pk])


class DeckUpdateView(LoginRequiredMixin, UpdateView):
    model = Deck
    fields = ["name", "language"]
    success_url = reverse_lazy("deck-list")

    def get_queryset(self):
        return self.request.user.decks.all()


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


class CardCreateView(UserDeckMixin, CreateView):
    model = Card
    fields = ["question", "answer", "box"]

    def form_valid(self, form):
        form.instance.deck = self.deck
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("card-create", args=[self.deck.pk])


class CardUpdateView(UserDeckMixin, UpdateView):
    model = Card
    fields = ["question", "answer", "box"]

    def get_queryset(self):
        return self.deck.cards.all()

    def get_success_url(self):
        return reverse("card-list", args=[self.deck.pk])


class StudyView(UserDeckMixin, ListView):
    """Quiz the user on a random card that is due today."""

    model = Card
    template_name = "cards/study.html"
    form_class = CardCheckForm

    def get_cards(self):
        return self.deck.cards.all()

    def get_queryset(self):
        return self.get_cards().filter(due_date__lte=timezone.localdate())

    def get_direction(self):
        direction = self.request.GET.get("direction")
        if direction in STUDY_DIRECTIONS:
            self.request.session["study_direction"] = direction
        return self.request.session.get("study_direction", "forward")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        direction = self.get_direction()
        context["direction"] = direction
        context["directions"] = STUDY_DIRECTIONS
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
