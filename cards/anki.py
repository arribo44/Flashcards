# cards/anki.py

"""Read the notes of an Anki package (.apkg) exported from Anki or AnkiWeb.

An .apkg file is a zip archive holding the collection as an SQLite database:
- "collection.anki21b" (Anki >= 2.1.50): zstd-compressed, note types in the
  `notetypes` and `fields` tables;
- "collection.anki21" or "collection.anki2" (older): plain SQLite, note types
  stored as JSON in `col.models`.
Media files are ignored: the app reads cards with speech synthesis.
"""

import html
import io
import json
import os
import re
import sqlite3
import tempfile
import zipfile
import zlib

import zstandard
from django.utils.html import strip_tags
from django.utils.translation import gettext as _

from .languages import names_for, plain

# The collection holds text only, so even big decks stay far below this:
# anything larger is most likely a zip bomb
MAX_COLLECTION_SIZE = 200 * 1024 * 1024
MAX_NOTES = 20000

COLLECTION_FILES = ("collection.anki21b", "collection.anki21", "collection.anki2")
FIELD_SEPARATOR = "\x1f"

SOUND_RE = re.compile(r"\[sound:[^\]]*\]")
CLOZE_RE = re.compile(r"\{\{c\d+::(.*?)(?:::[^}]*)?\}\}")
LINE_BREAK_RE = re.compile(r"<br\s*/?>|</(?:div|p|li)>", re.IGNORECASE)


class AnkiImportError(Exception):
    pass


def clean_field(value):
    """Turn an Anki field (HTML, sound tags, cloze markers) into plain text."""
    value = SOUND_RE.sub(" ", value)
    value = CLOZE_RE.sub(r"\1", value)
    value = LINE_BREAK_RE.sub(" ", value)
    value = html.unescape(strip_tags(value))
    return " ".join(value.split())


# Usual Anki field names for each role, best match first, in plain() form.
# A field named after the language studied or the user's language comes first.
FIELD_NAME_HINTS = {
    "question": ("front", "recto", "question", "word", "mot"),
    "answer": ("back", "verso", "answer", "reponse", "translation", "traduction", "meaning", "sens"),
}
# "Example" or "sentence" in English, French, Spanish, Italian, Portuguese and German
EXAMPLE_NAME_HINTS = ("example", "exemple", "ejemplo", "esempio", "exemplo", "beispiel",
                      "sentence", "phrase", "frase", "satz")


def numeric_fields(notes):
    """Return the indexes of fields that hold mostly bare numbers, such as ids."""
    if not notes:
        return set()
    width = len(notes[0])
    return {
        index for index in range(width)
        if sum(note[index].isdigit() for note in notes) > len(notes) / 2
    }


def suggest_mapping(field_names, notes, studied=None, native=None):
    """Guess which fields hold the question, the answer and the example.

    `studied` is the deck's language and `native` the user's, as ISO 639-1
    codes: a field named after one of them (e.g. "Italiano", "English") is the
    question or the answer.
    """
    names = [plain(name) for name in field_names]
    numeric = numeric_fields(notes)
    usable = [
        index for index in range(len(names))
        if index not in numeric and any(note[index] for note in notes)
    ]

    language_hints = {"question": names_for(studied), "answer": names_for(native)}
    mapping = {}
    for role, generic_hints in FIELD_NAME_HINTS.items():
        hints = [*sorted(language_hints[role]), *generic_hints]
        taken = set(mapping.values())
        mapping[role] = next(
            (
                names.index(hint) for hint in hints
                if hint in names and names.index(hint) in usable
                and names.index(hint) not in taken
            ),
            None,
        )
    # No telling name: fall back on the first fields that hold text
    for role in ("question", "answer"):
        if mapping[role] is None:
            taken = set(mapping.values())
            mapping[role] = next((i for i in usable if i not in taken), None)
    taken = set(mapping.values())
    mapping["example"] = next(
        (
            index for index in usable
            if index not in taken and any(hint in names[index] for hint in EXAMPLE_NAME_HINTS)
        ),
        None,
    )
    return mapping


def shorten(value, max_length):
    """Cut a too long text after its last " ; " or word that fits, adding "…"."""
    if len(value) <= max_length:
        return value
    cut = value[:max_length - 1]
    for separator in (" ; ", "; ", " "):
        position = cut.rfind(separator)
        if position > max_length // 2:
            cut = cut[:position]
            break
    return cut.rstrip(" ;,") + "…"


def read_apkg(uploaded_file):
    """Return the package's note types, each with its field names and notes.

    Result: [{"id": str, "name": str, "fields": [str], "notes": [[str]]}],
    note types without notes left out, the most used first.
    """
    collection = extract_collection(uploaded_file)
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as db_file:
        db_file.write(collection)
    try:
        connection = sqlite3.connect(f"file:{db_file.name}?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.create_collation("unicase", compare_unicase)
            note_types = read_note_types(connection)
            notes = connection.execute("SELECT mid, flds FROM notes ORDER BY id").fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        raise AnkiImportError(_("Le fichier Anki est illisible ou endommagé.")) from error
    finally:
        os.unlink(db_file.name)

    if len(notes) > MAX_NOTES:
        raise AnkiImportError(
            _("Ce paquet contient %(count)d notes : %(max)d au maximum par import.")
            % {"count": len(notes), "max": MAX_NOTES}
        )
    if len(notes) == 1 and "update to the latest anki" in notes[0][1].lower():
        # Placeholder note that new Anki versions put in the legacy collection
        raise AnkiImportError(
            _("Ce paquet n'a pas pu être lu : réexportez-le depuis Anki en cochant "
              "« Prise en charge des anciennes versions d'Anki ».")
        )

    for mid, fields in notes:
        note_type = note_types.get(str(mid))
        if note_type is None:
            continue
        values = [clean_field(value) for value in fields.split(FIELD_SEPARATOR)]
        width = len(note_type["fields"])
        note_type["notes"].append((values + [""] * width)[:width])

    used = [note_type for note_type in note_types.values() if note_type["notes"]]
    if not used:
        raise AnkiImportError(_("Ce paquet ne contient aucune note."))
    return sorted(used, key=lambda note_type: -len(note_type["notes"]))


def compare_unicase(left, right):
    # Case-insensitive collation that Anki declares on its name columns
    left, right = left.casefold(), right.casefold()
    return (left > right) - (left < right)


def extract_collection(uploaded_file):
    try:
        archive = zipfile.ZipFile(uploaded_file)
    except zipfile.BadZipFile as error:
        raise AnkiImportError(_("Ce fichier n'est pas un paquet Anki (.apkg).")) from error

    with archive:
        names = set(archive.namelist())
        name = next((name for name in COLLECTION_FILES if name in names), None)
        if name is None:
            raise AnkiImportError(_("Ce fichier n'est pas un paquet Anki (.apkg)."))
        try:
            with archive.open(name) as member:
                data = read_limited(member)
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as error:
            raise AnkiImportError(_("Le fichier Anki est illisible ou endommagé.")) from error

    if name.endswith("b"):
        try:
            reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data))
            data = read_limited(reader)
        except zstandard.ZstdError as error:
            raise AnkiImportError(_("Le fichier Anki est illisible ou endommagé.")) from error
    return data


def read_limited(stream):
    data = stream.read(MAX_COLLECTION_SIZE + 1)
    if len(data) > MAX_COLLECTION_SIZE:
        raise AnkiImportError(_("Ce paquet Anki est trop volumineux."))
    return data


def read_note_types(connection):
    """Map each note type id (as a string) to its name and ordered field names."""
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    note_types = {}
    if "notetypes" in tables:
        for ntid, name in connection.execute("SELECT id, name FROM notetypes"):
            note_types[str(ntid)] = {"id": str(ntid), "name": name, "fields": [], "notes": []}
        for ntid, name in connection.execute("SELECT ntid, name FROM fields ORDER BY ntid, ord"):
            if str(ntid) in note_types:
                note_types[str(ntid)]["fields"].append(name)
    else:
        (models,) = connection.execute("SELECT models FROM col").fetchone()
        for mid, model in json.loads(models).items():
            fields = sorted(model["flds"], key=lambda field: field["ord"])
            note_types[str(mid)] = {
                "id": str(mid),
                "name": model["name"],
                "fields": [field["name"] for field in fields],
                "notes": [],
            }
    return note_types
