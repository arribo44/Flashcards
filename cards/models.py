from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


NUM_BOXES = 5
BOXES = range(1, NUM_BOXES + 1)

# Days to wait before a card is due again, depending on the box it lands in.
# A card sent back to the first box is due again the same day.
REVIEW_INTERVALS = {1: 0, 2: 1, 3: 3, 4: 7, 5: 14}


class Deck(models.Model):
    class Language(models.TextChoices):
        ENGLISH = "en", "Anglais"
        SPANISH = "es", "Espagnol"

    # Voices used by the browser's speech synthesis to read the cards
    SPEECH_LANGS = {Language.ENGLISH: "en-GB", Language.SPANISH: "es-ES"}

    name = models.CharField("nom", max_length=100)
    language = models.CharField("langue", max_length=2, choices=Language.choices)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="decks",
        verbose_name="propriétaire",
    )
    date_created = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "paquet"

    def __str__(self):
        return self.name

    @property
    def speech_lang(self):
        return self.SPEECH_LANGS.get(self.language, self.language)


class Card(models.Model):
    deck = models.ForeignKey(
        Deck,
        on_delete=models.CASCADE,
        related_name="cards",
        verbose_name="paquet",
    )
    question = models.CharField("question", max_length=100)
    answer = models.CharField("réponse", max_length=100)
    example = models.CharField(
        "exemple",
        max_length=200,
        blank=True,
        help_text="Une phrase qui utilise la question en contexte (facultatif).",
    )
    box = models.IntegerField(
        "boîte",
        choices=zip(BOXES, BOXES),
        default=BOXES[0],
    )
    due_date = models.DateField("prochaine révision", default=timezone.localdate)
    last_reviewed = models.DateTimeField("dernière révision", null=True, blank=True)
    date_created = models.DateTimeField("créée le", auto_now_add=True)

    class Meta:
        verbose_name = "carte"

    def __str__(self):
        return self.question

    @property
    def is_due(self):
        return self.due_date <= timezone.localdate()

    def move(self, solved):
        new_box = self.box + 1 if solved else BOXES[0]

        if new_box in BOXES:
            self.box = new_box

        self.last_reviewed = timezone.now()
        self.due_date = timezone.localdate() + timedelta(
            days=REVIEW_INTERVALS[self.box]
        )
        self.save()

        return self
