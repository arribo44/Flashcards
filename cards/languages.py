# cards/languages.py

"""Languages a deck can be studied in.

To offer a new language, add it to LANGUAGES with its flag in
cards/static/cards/flags/, then translate its name and prompt (see README).
"""

import unicodedata
from typing import NamedTuple

from django.conf.locale import LANG_INFO
from django.utils import translation
from django.utils.translation import gettext_lazy as _


class StudyLanguage(NamedTuple):
    name: str
    # Shown above the card when reviewing from the translation
    reverse_prompt: str
    # Voice asked from the browser's speech synthesis
    speech_lang: str
    # Flag file in cards/static/cards/flags/
    flag: str


# Keyed by ISO 639-1 code
LANGUAGES = {
    "en": StudyLanguage(_("Anglais"), _("Traduisez en anglais"), "en-GB", "gb"),
    "es": StudyLanguage(_("Espagnol"), _("Traduisez en espagnol"), "es-ES", "es"),
    "de": StudyLanguage(_("Allemand"), _("Traduisez en allemand"), "de-DE", "de"),
    "it": StudyLanguage(_("Italien"), _("Traduisez en italien"), "it-IT", "it"),
    "pt": StudyLanguage(_("Portugais"), _("Traduisez en portugais"), "pt-PT", "pt"),
    "ar": StudyLanguage(_("Arabe"), _("Traduisez en arabe"), "ar-SA", "arab"),
    "ca": StudyLanguage(_("Catalan"), _("Traduisez en catalan"), "ca-ES", "es-ct"),
    "zh": StudyLanguage(_("Chinois"), _("Traduisez en chinois"), "zh-CN", "cn"),
    "ko": StudyLanguage(_("Coréen"), _("Traduisez en coréen"), "ko-KR", "kr"),
    "da": StudyLanguage(_("Danois"), _("Traduisez en danois"), "da-DK", "dk"),
    "fi": StudyLanguage(_("Finnois"), _("Traduisez en finnois"), "fi-FI", "fi"),
    "fr": StudyLanguage(_("Français"), _("Traduisez en français"), "fr-FR", "fr"),
    "el": StudyLanguage(_("Grec"), _("Traduisez en grec"), "el-GR", "gr"),
    "he": StudyLanguage(_("Hébreu"), _("Traduisez en hébreu"), "he-IL", "il"),
    "hi": StudyLanguage(_("Hindi"), _("Traduisez en hindi"), "hi-IN", "in"),
    "hu": StudyLanguage(_("Hongrois"), _("Traduisez en hongrois"), "hu-HU", "hu"),
    "id": StudyLanguage(_("Indonésien"), _("Traduisez en indonésien"), "id-ID", "id"),
    "ja": StudyLanguage(_("Japonais"), _("Traduisez en japonais"), "ja-JP", "jp"),
    "nl": StudyLanguage(_("Néerlandais"), _("Traduisez en néerlandais"), "nl-NL", "nl"),
    "nb": StudyLanguage(_("Norvégien"), _("Traduisez en norvégien"), "nb-NO", "no"),
    "pl": StudyLanguage(_("Polonais"), _("Traduisez en polonais"), "pl-PL", "pl"),
    "ro": StudyLanguage(_("Roumain"), _("Traduisez en roumain"), "ro-RO", "ro"),
    "ru": StudyLanguage(_("Russe"), _("Traduisez en russe"), "ru-RU", "ru"),
    "sv": StudyLanguage(_("Suédois"), _("Traduisez en suédois"), "sv-SE", "se"),
    "cs": StudyLanguage(_("Tchèque"), _("Traduisez en tchèque"), "cs-CZ", "cz"),
    "th": StudyLanguage(_("Thaï"), _("Traduisez en thaï"), "th-TH", "th"),
    "tr": StudyLanguage(_("Turc"), _("Traduisez en turc"), "tr-TR", "tr"),
    "uk": StudyLanguage(_("Ukrainien"), _("Traduisez en ukrainien"), "uk-UA", "ua"),
    "vi": StudyLanguage(_("Vietnamien"), _("Traduisez en vietnamien"), "vi-VN", "vn"),
}

# Listed first when choosing a deck's language
COMMON = ["en", "es", "de", "it", "pt"]


def sort_key(text):
    """Alphabetical order that ignores accents and case (Égyptien next to Espagnol)."""
    return unicodedata.normalize("NFD", str(text)).encode("ascii", "ignore").decode().lower()


def choices():
    """Choices for a deck's language: common languages, then the others by name.

    A callable, so the names are sorted in the language of the interface.
    """
    others = sorted(
        (code for code in LANGUAGES if code not in COMMON),
        key=lambda code: sort_key(LANGUAGES[code].name),
    )
    return [
        (_("Langues courantes"), [(code, LANGUAGES[code].name) for code in COMMON]),
        (_("Autres langues"), [(code, LANGUAGES[code].name) for code in others]),
    ]


def plain(text):
    """Text without accents or case, to compare names ("Français" == "francais")."""
    decomposed = unicodedata.normalize("NFD", str(text))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold().strip()


def names_for(code):
    """The names a field holding this language may have, e.g. it, Italian, Italien, italiano.

    Returned in plain() form. Empty for an unknown or missing code.
    """
    if not code:
        return set()
    # "id" (Indonesian) would also match the "Id" field of many decks
    names = {code} if code != "id" else set()
    info = LANG_INFO.get(code, {})
    names.update(filter(None, (info.get("name"), info.get("name_local"))))
    if code in LANGUAGES:
        for interface_language in ("en", "fr"):
            with translation.override(interface_language):
                names.add(str(LANGUAGES[code].name))
    return {plain(name) for name in names}
