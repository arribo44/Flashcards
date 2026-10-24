import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0003_assign_existing_cards"),
    ]

    operations = [
        migrations.AlterField(
            model_name="card",
            name="deck",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cards", to="cards.deck"),
        ),
    ]
