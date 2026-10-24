# cards/forms.py

import csv
import io

from django import forms

from .models import Card


class CardCheckForm(forms.Form):
    card_id = forms.IntegerField(required=True)
    solved = forms.BooleanField(required=False)


class CardImportForm(forms.Form):
    MAX_FILE_SIZE = 1024 * 1024
    MAX_ERRORS_SHOWN = 10

    csv_file = forms.FileField(
        label="Fichier CSV",
        help_text=(
            "Colonnes : question, réponse et, si vous voulez, un exemple. "
            "Séparateur virgule, point-virgule ou tabulation. Une ligne "
            "d'en-tête « question » est ignorée."
        ),
    )

    def clean_csv_file(self):
        """Return the file's cards as a list of (question, answer, example) tuples."""
        uploaded = self.cleaned_data["csv_file"]
        if uploaded.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError("Le fichier dépasse 1 Mo.")

        text = self.decode(uploaded.read())
        delimiter = self.guess_delimiter(text)

        fields = [Card._meta.get_field(name) for name in ("question", "answer", "example")]
        cards = []
        errors = []
        for line_num, row in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
            cells = [cell.strip() for cell in row]
            if not any(cells):
                continue
            if not cards and not errors and cells[0].lower() == "question":
                continue
            if len(cells) < 2 or not cells[0] or not cells[1]:
                errors.append(f"Ligne {line_num} : il faut une question et une réponse.")
                continue
            values = (cells + [""])[:3]
            too_long = [
                f"{field.verbose_name} ({field.max_length} caractères max.)"
                for field, value in zip(fields, values)
                if len(value) > field.max_length
            ]
            if too_long:
                errors.append(f"Ligne {line_num} : trop long pour {', '.join(too_long)}.")
            else:
                cards.append(tuple(values))

        if errors:
            hidden = len(errors) - self.MAX_ERRORS_SHOWN
            if hidden > 0:
                errors = errors[:self.MAX_ERRORS_SHOWN] + [f"… et {hidden} autre(s) erreur(s)."]
            raise forms.ValidationError(errors)
        if not cards:
            raise forms.ValidationError("Le fichier ne contient aucune carte.")
        return cards

    @staticmethod
    def guess_delimiter(text):
        # csv.Sniffer gives up when rows have different lengths, which happens
        # with the optional example column: count delimiters on the first line
        first_line = next((line for line in text.splitlines() if line.strip()), "")
        return max(";\t,", key=first_line.count)

    @staticmethod
    def decode(raw):
        # Excel on Windows saves CSV files as cp1252 rather than UTF-8
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                pass
        raise forms.ValidationError("Encodage du fichier non reconnu : enregistrez-le en UTF-8.")
