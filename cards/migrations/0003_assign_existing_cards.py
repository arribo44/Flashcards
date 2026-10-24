from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def assign_existing_cards(apps, schema_editor):
    """Put cards created before decks existed into a default English deck.

    The deck goes to the first superuser (or first user). If there is no
    user at all, an "admin" superuser with an unusable password is created:
    set one with `manage.py changepassword admin`.
    """
    Card = apps.get_model("cards", "Card")
    Deck = apps.get_model("cards", "Deck")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    orphans = Card.objects.filter(deck__isnull=True)
    if not orphans.exists():
        return

    owner = (
        User.objects.filter(is_superuser=True).order_by("pk").first()
        or User.objects.order_by("pk").first()
    )
    if owner is None:
        owner = User.objects.create(
            username="admin",
            is_staff=True,
            is_superuser=True,
            password=make_password(None),
        )

    deck = Deck.objects.create(name="English vocabulary", language="en", owner=owner)
    orphans.update(deck=deck)


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0002_deck"),
    ]

    operations = [
        migrations.RunPython(assign_existing_cards, migrations.RunPython.noop),
    ]
