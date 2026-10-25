# cards/forms.py

import csv
import io

from django import forms
from django.conf import settings
from django.template.defaultfilters import filesizeformat
from django.utils.translation import get_language, gettext as _, gettext_lazy

from . import anki
from .models import Card


class CardCheckForm(forms.Form):
    card_id = forms.IntegerField(required=True)
    solved = forms.BooleanField(required=False)


class CardImportForm(forms.Form):
    MAX_FILE_SIZE = 1024 * 1024
    MAX_ERRORS_SHOWN = 10

    csv_file = forms.FileField(
        label=gettext_lazy("Fichier CSV"),
        help_text=gettext_lazy(
            "Colonnes : question, réponse et, si vous voulez, un exemple. "
            "Séparateur virgule, point-virgule ou tabulation. Une ligne "
            "d'en-tête « question » est ignorée."
        ),
    )

    def clean_csv_file(self):
        """Return the file's cards as a list of (question, answer, example) tuples."""
        uploaded = self.cleaned_data["csv_file"]
        if uploaded.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError(_("Le fichier dépasse 1 Mo."))

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
                errors.append(_("Ligne %(line)d : il faut une question et une réponse.") % {"line": line_num})
                continue
            values = (cells + [""])[:3]
            too_long = [
                _("%(field)s (%(max)d caractères max.)") % {
                    "field": field.verbose_name, "max": field.max_length
                }
                for field, value in zip(fields, values)
                if len(value) > field.max_length
            ]
            if too_long:
                errors.append(_("Ligne %(line)d : trop long pour %(fields)s.") % {
                    "line": line_num, "fields": ", ".join(too_long)
                })
            else:
                cards.append(tuple(values))

        if errors:
            hidden = len(errors) - self.MAX_ERRORS_SHOWN
            if hidden > 0:
                errors = errors[:self.MAX_ERRORS_SHOWN] + [
                    _("… et %(count)d autre(s) erreur(s).") % {"count": hidden}
                ]
            raise forms.ValidationError(errors)
        if not cards:
            raise forms.ValidationError(_("Le fichier ne contient aucune carte."))
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
        raise forms.ValidationError(_("Encodage du fichier non reconnu : enregistrez-le en UTF-8."))


class AnkiUploadForm(forms.Form):
    """Pick an .apkg file from settings.ANKI_FOLDER, or upload one.

    Once valid, cleaned_data holds the package's "note_types" (see
    anki.read_apkg) and its "file_name".
    """

    MAX_FILE_SIZE = 300 * 1024 * 1024

    local_file = forms.ChoiceField(label=gettext_lazy("Paquet du dossier"), required=False)
    apkg_file = forms.FileField(
        label=gettext_lazy("Paquet Anki (.apkg)"),
        help_text=gettext_lazy("Fichier téléchargé depuis AnkiWeb ou exporté depuis Anki. 300 Mo au maximum."),
        widget=forms.ClearableFileInput(attrs={"accept": ".apkg"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        local_files = self.local_files()
        if local_files:
            self.fields["local_file"].choices = [("", _("— Choisir un paquet —"))] + [
                (path.name, f"{path.name} ({filesizeformat(path.stat().st_size)})")
                for path in local_files
            ]
            self.fields["local_file"].help_text = _("Paquets trouvés dans %(folder)s.") % {
                "folder": self.folder_label()
            }
            self.fields["apkg_file"].label = _("ou envoyer un fichier")
        else:
            del self.fields["local_file"]

    @staticmethod
    def local_files():
        folder = settings.ANKI_FOLDER
        if not folder.is_dir():
            return []
        return sorted(
            (path for path in folder.iterdir() if path.suffix.lower() == ".apkg" and path.is_file()),
            key=lambda path: path.name.lower(),
        )

    @staticmethod
    def folder_label():
        folder = settings.ANKI_FOLDER
        return str(folder.relative_to(settings.BASE_DIR) if folder.is_relative_to(settings.BASE_DIR) else folder)

    def clean(self):
        cleaned_data = super().clean()
        local_name = cleaned_data.get("local_file")
        uploaded = cleaned_data.get("apkg_file")
        if self.errors:
            return cleaned_data
        if local_name and uploaded:
            raise forms.ValidationError(_("Choisissez un paquet du dossier ou envoyez un fichier, pas les deux."))
        if not local_name and not uploaded:
            raise forms.ValidationError(_("Choisissez un paquet Anki (.apkg)."))
        try:
            if local_name:
                # The name comes from the field's choices: it can't leave the folder
                with open(settings.ANKI_FOLDER / local_name, "rb") as local_file:
                    cleaned_data["note_types"] = anki.read_apkg(local_file)
                cleaned_data["file_name"] = local_name
            else:
                cleaned_data["note_types"] = anki.read_apkg(uploaded)
                cleaned_data["file_name"] = uploaded.name
        except anki.AnkiImportError as error:
            raise forms.ValidationError(str(error)) from error
        return cleaned_data

    def clean_apkg_file(self):
        uploaded = self.cleaned_data["apkg_file"]
        if not uploaded:
            return None
        if not uploaded.name.lower().endswith(".apkg"):
            raise forms.ValidationError(_("Choisissez un fichier .apkg."))
        if uploaded.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError(_("Le fichier dépasse 300 Mo."))
        return uploaded


class AnkiMappingForm(forms.Form):
    """Choose which Anki fields become the question, answer and example."""

    question = forms.TypedChoiceField(label=gettext_lazy("Question (langue étudiée)"), coerce=int)
    answer = forms.TypedChoiceField(label=gettext_lazy("Réponse (traduction)"), coerce=int)
    example = forms.TypedChoiceField(
        label=gettext_lazy("Exemple"), coerce=int, empty_value=None, required=False
    )

    def __init__(self, *args, field_names, notes, studied=None, **kwargs):
        """`studied` is the deck's language, to recognise the field that holds it."""
        super().__init__(*args, **kwargs)
        self.field_names = field_names
        self.numeric = anki.numeric_fields(notes)
        # Show each field with its first non-empty value, to tell them apart
        sample = [
            next((note[index] for note in notes if note[index]), "")
            for index in range(len(field_names))
        ]
        choices = [
            (index, _("%(field)s — « %(sample)s »") % {
                "field": name, "sample": value[:40] + ("…" if len(value) > 40 else "")
            } if value else name)
            for index, (name, value) in enumerate(zip(field_names, sample))
        ]
        self.fields["question"].choices = choices
        self.fields["answer"].choices = choices
        self.fields["example"].choices = [("", _("— Aucun —"))] + choices
        # The answers are most likely in the user's language: that of the interface
        native = get_language().split("-")[0]
        for role, index in anki.suggest_mapping(field_names, notes, studied, native).items():
            self.initial.setdefault(role, index)

    def clean(self):
        cleaned_data = super().clean()
        for role in ("question", "answer"):
            index = cleaned_data.get(role)
            if index in self.numeric:
                self.add_error(role, _(
                    "Le champ « %(field)s » ne contient presque que des "
                    "nombres : c'est sans doute un identifiant. Choisissez un autre champ."
                ) % {"field": self.field_names[index]})
        chosen = [cleaned_data.get(name) for name in ("question", "answer", "example")]
        chosen = [index for index in chosen if index is not None]
        if len(chosen) != len(set(chosen)):
            raise forms.ValidationError(_("Choisissez un champ différent pour chaque rôle."))
        return cleaned_data
