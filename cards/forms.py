# cards/forms.py

import csv
import io

from django import forms

from . import anki
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


class AnkiUploadForm(forms.Form):
    MAX_FILE_SIZE = 300 * 1024 * 1024

    apkg_file = forms.FileField(
        label="Paquet Anki (.apkg)",
        help_text="Fichier téléchargé depuis AnkiWeb ou exporté depuis Anki. 300 Mo au maximum.",
        widget=forms.ClearableFileInput(attrs={"accept": ".apkg"}),
    )

    def clean_apkg_file(self):
        """Return the package's note types (see anki.read_apkg)."""
        uploaded = self.cleaned_data["apkg_file"]
        if not uploaded.name.lower().endswith(".apkg"):
            raise forms.ValidationError("Choisissez un fichier .apkg.")
        if uploaded.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError("Le fichier dépasse 300 Mo.")
        try:
            return anki.read_apkg(uploaded)
        except anki.AnkiImportError as error:
            raise forms.ValidationError(str(error)) from error


class AnkiMappingForm(forms.Form):
    """Choose which Anki fields become the question, answer and example."""

    question = forms.TypedChoiceField(label="Question (langue étudiée)", coerce=int)
    answer = forms.TypedChoiceField(label="Réponse (traduction)", coerce=int)
    example = forms.TypedChoiceField(
        label="Exemple", coerce=int, empty_value=None, required=False
    )

    def __init__(self, *args, field_names, notes, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_names = field_names
        self.numeric = anki.numeric_fields(notes)
        # Show each field with its first non-empty value, to tell them apart
        sample = [
            next((note[index] for note in notes if note[index]), "")
            for index in range(len(field_names))
        ]
        choices = [
            (index, f"{name} — « {value[:40]}{'…' if len(value) > 40 else ''} »" if value else name)
            for index, (name, value) in enumerate(zip(field_names, sample))
        ]
        self.fields["question"].choices = choices
        self.fields["answer"].choices = choices
        self.fields["example"].choices = [("", "— Aucun —")] + choices
        for role, index in anki.suggest_mapping(field_names, notes).items():
            self.initial.setdefault(role, index)

    def clean(self):
        cleaned_data = super().clean()
        for role in ("question", "answer"):
            index = cleaned_data.get(role)
            if index in self.numeric:
                self.add_error(role, (
                    f"Le champ « {self.field_names[index]} » ne contient presque que des "
                    "nombres : c'est sans doute un identifiant. Choisissez un autre champ."
                ))
        chosen = [cleaned_data.get(name) for name in ("question", "answer", "example")]
        chosen = [index for index in chosen if index is not None]
        if len(chosen) != len(set(chosen)):
            raise forms.ValidationError("Choisissez un champ différent pour chaque rôle.")
        return cleaned_data
