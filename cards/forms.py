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
            "Deux colonnes : question puis réponse. Séparateur virgule, "
            "point-virgule ou tabulation. Une ligne d'en-tête « question » "
            "est ignorée."
        ),
    )

    def clean_csv_file(self):
        """Return the file's cards as a list of (question, answer) pairs."""
        uploaded = self.cleaned_data["csv_file"]
        if uploaded.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError("Le fichier dépasse 1 Mo.")

        text = self.decode(uploaded.read())
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        max_length = Card._meta.get_field("question").max_length
        cards = []
        errors = []
        for line_num, row in enumerate(csv.reader(io.StringIO(text), dialect), start=1):
            cells = [cell.strip() for cell in row]
            if not any(cells):
                continue
            if not cards and not errors and cells[0].lower() == "question":
                continue
            if len(cells) < 2 or not cells[0] or not cells[1]:
                errors.append(f"Ligne {line_num} : il faut une question et une réponse.")
            elif len(cells[0]) > max_length or len(cells[1]) > max_length:
                errors.append(f"Ligne {line_num} : {max_length} caractères maximum par champ.")
            else:
                cards.append((cells[0], cells[1]))

        if errors:
            hidden = len(errors) - self.MAX_ERRORS_SHOWN
            if hidden > 0:
                errors = errors[:self.MAX_ERRORS_SHOWN] + [f"… et {hidden} autre(s) erreur(s)."]
            raise forms.ValidationError(errors)
        if not cards:
            raise forms.ValidationError("Le fichier ne contient aucune carte.")
        return cards

    @staticmethod
    def decode(raw):
        # Excel on Windows saves CSV files as cp1252 rather than UTF-8
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                pass
        raise forms.ValidationError("Encodage du fichier non reconnu : enregistrez-le en UTF-8.")
