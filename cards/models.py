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
        ENGLISH = "en", "English"
        SPANISH = "es", "Spanish"

    name = models.CharField(max_length=100)
    language = models.CharField(max_length=2, choices=Language.choices)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="decks",
    )
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Card(models.Model):
    deck = models.ForeignKey(
        Deck,
        on_delete=models.CASCADE,
        related_name="cards",
    )
    question = models.CharField(max_length=100)
    answer = models.CharField(max_length=100)
    box = models.IntegerField(
        choices=zip(BOXES, BOXES),
        default=BOXES[0],
    )
    due_date = models.DateField(default=timezone.localdate)
    last_reviewed = models.DateTimeField(null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

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
