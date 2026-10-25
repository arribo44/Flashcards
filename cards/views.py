# cards/views.py

import random

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Min, Q
from django.urls import reverse, reverse_lazy
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy, ngettext_lazy

from django.shortcuts import get_object_or_404, redirect

from django.views.generic import (
    ListView,
    CreateView,
    DeleteView,
    FormView,
    TemplateView,
    UpdateView,
)

from . import anki, stats
from .models import BOXES, Card, Deck, Review
from .forms import AnkiMappingForm, AnkiUploadForm, CardCheckForm, CardImportForm


STUDY_DIRECTIONS = {
    "forward": gettext_lazy("Question → Réponse"),
    "reverse": gettext_lazy("Réponse → Question"),
    "mixed": gettext_lazy("Mélangé"),
}

ANSWER_MODES = {
    "reveal": gettext_lazy("Révéler la réponse"),
    "type": gettext_lazy("Taper la réponse"),
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
            **{
                f"box_{box}": Count("cards", filter=Q(cards__box=box))
                for box in BOXES
            },
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for deck in context["deck_list"]:
            deck.box_shares = [
                {
                    "number": box,
                    "count": getattr(deck, f"box_{box}"),
                    "percent": 100 * getattr(deck, f"box_{box}") / deck.card_count
                    if deck.card_count else 0,
                }
                for box in BOXES
            ]
        days = stats.review_days(Review.objects.filter(deck__owner=self.request.user))
        context["streak"] = stats.current_streak(days, timezone.localdate())
        return context


class StatsView(LoginRequiredMixin, TemplateView):
    template_name = "cards/stats.html"
    CHART_DAYS = 14
    SUCCESS_RATE_DAYS = 30

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        reviews = Review.objects.filter(deck__owner=self.request.user)
        cards = Card.objects.filter(deck__owner=self.request.user)

        days = stats.review_days(reviews)
        context["streak"] = stats.current_streak(days, today)
        context["best_streak"] = stats.longest_streak(days)
        context["reviewed_today"] = today in days

        recent = reviews.filter(
            reviewed_at__date__gt=today - timedelta(days=self.SUCCESS_RATE_DAYS)
        ).aggregate(total=Count("id"), solved=Count("id", filter=Q(solved=True)))
        context["recent_total"] = recent["total"]
        context["success_rate"] = (
            round(100 * recent["solved"] / recent["total"]) if recent["total"] else None
        )
        context["success_rate_days"] = self.SUCCESS_RATE_DAYS

        context["due_today"] = cards.filter(due_date__lte=today).count()
        context["mastered"] = cards.filter(box=BOXES[-1]).count()
        context["card_total"] = cards.count()

        daily = stats.daily_counts(reviews, today, self.CHART_DAYS)
        busiest = max(day["total"] for day in daily)
        for day in daily:
            day["height"] = round(100 * day["total"] / busiest) if busiest else 0
            day["is_today"] = day["date"] == today
        context["daily"] = daily
        context["daily_total"] = sum(day["total"] for day in daily)
        context["busiest"] = busiest

        decks = self.request.user.decks.annotate(
            due_count=Count("cards", filter=Q(cards__due_date__lte=today)),
            **{
                f"box_{box}": Count("cards", filter=Q(cards__box=box))
                for box in BOXES
            },
        )
        for deck in decks:
            deck.box_counts = [getattr(deck, f"box_{box}") for box in BOXES]
        context["decks"] = decks
        context["boxes"] = BOXES
        return context


class DeckCreateView(SuccessMessageMixin, LoginRequiredMixin, CreateView):
    model = Deck
    fields = ["name", "language"]
    success_message = gettext_lazy("Paquet « %(name)s » créé.")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("card-list", args=[self.object.pk])


class DeckUpdateView(SuccessMessageMixin, LoginRequiredMixin, UpdateView):
    model = Deck
    fields = ["name", "language"]
    success_url = reverse_lazy("deck-list")
    success_message = gettext_lazy("Paquet « %(name)s » enregistré.")

    def get_queryset(self):
        return self.request.user.decks.all()


class DeckDeleteView(SuccessMessageMixin, LoginRequiredMixin, DeleteView):
    model = Deck
    success_url = reverse_lazy("deck-list")

    def get_queryset(self):
        return self.request.user.decks.annotate(card_count=Count("cards"))

    def get_success_message(self, cleaned_data):
        return _("Paquet « %(name)s » supprimé.") % {"name": self.object.name}


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
    paginate_by = 25

    def get_queryset(self):
        cards = self.deck.cards.order_by("box", "-date_created")
        query = self.request.GET.get("q", "").strip()
        if query:
            cards = cards.filter(
                Q(question__icontains=query)
                | Q(answer__icontains=query)
                | Q(example__icontains=query)
            )
        return cards

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        return context


class CardCreateView(SuccessMessageMixin, UserDeckMixin, CreateView):
    model = Card
    fields = ["question", "answer", "example", "box"]
    success_message = gettext_lazy("Carte « %(question)s » ajoutée.")

    def form_valid(self, form):
        form.instance.deck = self.deck
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("card-create", args=[self.deck.pk])


class CardUpdateView(SuccessMessageMixin, UserDeckMixin, UpdateView):
    model = Card
    fields = ["question", "answer", "example", "box"]
    success_message = gettext_lazy("Carte « %(question)s » enregistrée.")

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
        return _("Carte « %(question)s » supprimée.") % {"question": self.object.question}


def add_cards(deck, rows):
    """Create cards from (question, answer, example) rows, skipping known questions.

    Return the number of cards created.
    """
    known_questions = set(deck.cards.values_list("question", flat=True))
    new_cards = []
    for question, answer, example in rows:
        if question not in known_questions:
            known_questions.add(question)
            new_cards.append(Card(deck=deck, question=question, answer=answer, example=example))
    Card.objects.bulk_create(new_cards)
    return len(new_cards)


SKIPPED_MESSAGES = {
    "known": ngettext_lazy(
        "%(count)d ignorée (déjà présente).", "%(count)d ignorées (déjà présentes).", "count"
    ),
    "empty": ngettext_lazy(
        "%(count)d ignorée (question ou réponse vide).",
        "%(count)d ignorées (question ou réponse vide).",
        "count",
    ),
    "too_long": ngettext_lazy(
        "%(count)d ignorée (trop longue).", "%(count)d ignorées (trop longues).", "count"
    ),
}


def import_summary(imported, **skipped):
    """Build e.g. "12 cartes importées. 2 ignorées (déjà présentes)."."""
    message = ngettext_lazy(
        "%(count)d carte importée.", "%(count)d cartes importées.", "count"
    ) % {"count": imported}
    for reason, count in skipped.items():
        if count:
            message += " " + SKIPPED_MESSAGES[reason] % {"count": count}
    return message


class CardImportView(UserDeckMixin, FormView):
    """Add cards to the deck from a CSV file, skipping questions it already has."""

    form_class = CardImportForm
    template_name = "cards/card_import.html"

    def form_valid(self, form):
        rows = form.cleaned_data["csv_file"]
        imported = add_cards(self.deck, rows)
        messages.success(
            self.request,
            import_summary(imported, known=len(rows) - imported),
        )
        return redirect("card-list", deck_pk=self.deck.pk)


ANKI_SESSION_KEY = "anki_import"


class AnkiUploadView(UserDeckMixin, FormView):
    """First step of an Anki import: read the chosen .apkg and keep its notes in the session."""

    form_class = AnkiUploadForm
    template_name = "cards/anki_upload.html"

    def form_valid(self, form):
        self.request.session[ANKI_SESSION_KEY] = {
            "deck": self.deck.pk,
            "file_name": form.cleaned_data["file_name"],
            "note_types": form.cleaned_data["note_types"],
        }
        return redirect("anki-map", deck_pk=self.deck.pk)


class AnkiMapView(UserDeckMixin, FormView):
    """Second step: pick the note type and the fields to use, then create the cards."""

    form_class = AnkiMappingForm
    template_name = "cards/anki_map.html"
    PREVIEW_SIZE = 5

    def dispatch(self, request, *args, **kwargs):
        pending = request.session.get(ANKI_SESSION_KEY)
        if request.user.is_authenticated and (
            not pending or pending["deck"] != kwargs["deck_pk"]
        ):
            return redirect("anki-upload", deck_pk=kwargs["deck_pk"])
        self.pending = pending
        return super().dispatch(request, *args, **kwargs)

    def get_note_type(self):
        note_types = self.pending["note_types"]
        wanted = self.request.POST.get("note_type") or self.request.GET.get("note_type")
        return next((nt for nt in note_types if nt["id"] == wanted), note_types[0])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        note_type = self.get_note_type()
        kwargs.update(
            field_names=note_type["fields"], notes=note_type["notes"], studied=self.deck.language
        )
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        note_type = self.get_note_type()
        context["note_type"] = note_type
        context["note_types"] = self.pending["note_types"]
        context["file_name"] = self.pending["file_name"]
        context["preview"] = note_type["notes"][:self.PREVIEW_SIZE]
        return context

    def form_valid(self, form):
        note_type = self.get_note_type()
        q, a, ex = (form.cleaned_data[name] for name in ("question", "answer", "example"))
        limits = {
            name: Card._meta.get_field(name).max_length
            for name in ("question", "answer", "example")
        }
        rows, empty, too_long = [], 0, 0
        for note in note_type["notes"]:
            question, answer = note[q], note[a]
            # The example is optional: shorten it rather than lose the card
            example = anki.shorten(note[ex], limits["example"]) if ex is not None else ""
            if not question or not answer:
                empty += 1
            elif len(question) > limits["question"] or len(answer) > limits["answer"]:
                too_long += 1
            else:
                rows.append((question, answer, example))

        imported = add_cards(self.deck, rows)
        del self.request.session[ANKI_SESSION_KEY]
        messages.success(self.request, import_summary(
            imported, known=len(rows) - imported, empty=empty, too_long=too_long
        ))
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
            # Changing the direction or answer mode keeps the card on screen.
            kept = [c for c in self.object_list if str(c.pk) == self.request.GET.get("card")]
            context["check_card"] = kept[0] if kept else random.choice(self.object_list)
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
