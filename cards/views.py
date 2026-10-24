# cards/views.py

import random

from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.urls import reverse, reverse_lazy

from django.shortcuts import get_object_or_404, redirect

from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
)

from .models import Card, Deck
from .forms import CardCheckForm


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
        return self.request.user.decks.annotate(card_count=Count("cards"))


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


class BoxView(CardListView):
    template_name = "cards/box.html"
    form_class = CardCheckForm

    def get_queryset(self):
        return self.deck.cards.filter(box=self.kwargs["box_num"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["box_number"] = self.kwargs["box_num"]
        if self.object_list:
            context["check_card"] = random.choice(self.object_list)
        return context


    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            card = get_object_or_404(self.deck.cards, id=form.cleaned_data["card_id"])
            card.move(form.cleaned_data["solved"])

        return redirect("box", deck_pk=self.deck.pk, box_num=self.kwargs["box_num"])
