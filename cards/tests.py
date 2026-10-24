import io
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import timedelta

import zstandard

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import anki, stats
from .models import Card, Deck, NUM_BOXES, REVIEW_INTERVALS, Review


class CardMoveTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user("alice", password="pw")
        self.deck = Deck.objects.create(name="Words", language="en", owner=owner)

    def test_solved_moves_to_next_box(self):
        card = Card.objects.create(deck=self.deck, question="q", answer="a", box=2)
        self.assertEqual(card.move(True).box, 3)

    def test_unsolved_goes_back_to_first_box(self):
        card = Card.objects.create(deck=self.deck, question="q", answer="a", box=4)
        self.assertEqual(card.move(False).box, 1)

    def test_solved_in_last_box_stays(self):
        card = Card.objects.create(deck=self.deck, question="q", answer="a", box=NUM_BOXES)
        self.assertEqual(card.move(True).box, NUM_BOXES)

    def test_new_card_is_due_today(self):
        card = Card.objects.create(deck=self.deck, question="q", answer="a")
        self.assertTrue(card.is_due)

    def test_move_schedules_next_review(self):
        today = timezone.localdate()
        card = Card.objects.create(deck=self.deck, question="q", answer="a", box=2)
        card.move(True)
        card.refresh_from_db()
        self.assertEqual(card.due_date, today + timedelta(days=REVIEW_INTERVALS[3]))
        self.assertFalse(card.is_due)
        self.assertIsNotNone(card.last_reviewed)

    def test_failed_card_is_due_again_today(self):
        card = Card.objects.create(deck=self.deck, question="q", answer="a", box=4)
        card.move(False)
        self.assertTrue(card.is_due)

    def test_example_lines(self):
        card = Card(example="I hate him ; a deep hatred;  ; out of hatred")
        self.assertEqual(card.example_lines, ["I hate him", "a deep hatred", "out of hatred"])
        self.assertEqual(Card(example="").example_lines, [])

    def test_move_records_review_kept_after_card_deletion(self):
        card = Card.objects.create(deck=self.deck, question="q", answer="a")
        card.move(True)
        card.move(False)
        self.assertEqual(
            list(Review.objects.order_by("pk").values_list("solved", flat=True)), [True, False]
        )
        card.delete()
        self.assertEqual(self.deck.reviews.count(), 2)


class StreakTests(TestCase):
    today = timezone.localdate()

    def days(self, *offsets):
        return {self.today - timedelta(days=offset) for offset in offsets}

    def test_streak_including_today(self):
        self.assertEqual(stats.current_streak(self.days(0, 1, 2, 4), self.today), 3)

    def test_streak_still_open_when_today_not_reviewed_yet(self):
        self.assertEqual(stats.current_streak(self.days(1, 2), self.today), 2)

    def test_streak_broken_by_missed_day(self):
        self.assertEqual(stats.current_streak(self.days(2, 3), self.today), 0)

    def test_longest_streak(self):
        self.assertEqual(stats.longest_streak(self.days(0, 3, 4, 5, 6, 9, 10)), 4)
        self.assertEqual(stats.longest_streak(set()), 0)


class AccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.deck = Deck.objects.create(name="Alice EN", language="en", owner=self.alice)
        self.card = Card.objects.create(deck=self.deck, question="q", answer="a", box=1)
        self.bob_deck = Deck.objects.create(name="Bob ES", language="es", owner=self.bob)

    def deck_urls(self):
        return [
            reverse("card-list", args=[self.deck.pk]),
            reverse("card-create", args=[self.deck.pk]),
            reverse("card-update", args=[self.deck.pk, self.card.pk]),
            reverse("box", args=[self.deck.pk, 1]),
            reverse("study", args=[self.deck.pk]),
            reverse("card-delete", args=[self.deck.pk, self.card.pk]),
            reverse("card-import", args=[self.deck.pk]),
            reverse("anki-upload", args=[self.deck.pk]),
            reverse("deck-update", args=[self.deck.pk]),
            reverse("deck-delete", args=[self.deck.pk]),
        ]

    def test_anonymous_is_redirected_to_login(self):
        for url in [reverse("deck-list"), *self.deck_urls()]:
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_owner_can_access_own_deck(self):
        self.client.force_login(self.alice)
        for url in self.deck_urls():
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_other_user_gets_404(self):
        self.client.force_login(self.bob)
        for url in self.deck_urls():
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_deck_list_shows_only_own_decks(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("deck-list"))
        self.assertContains(response, "Bob ES")
        self.assertNotContains(response, "Alice EN")

    def test_cannot_move_card_through_another_deck(self):
        self.client.force_login(self.bob)
        response = self.client.post(
            reverse("box", args=[self.bob_deck.pk, 1]),
            {"card_id": self.card.pk, "solved": "True"},
        )
        self.assertEqual(response.status_code, 404)
        self.card.refresh_from_db()
        self.assertEqual(self.card.box, 1)

    def test_study_moves_card_and_redirects_to_box(self):
        self.client.force_login(self.alice)
        url = reverse("box", args=[self.deck.pk, 1])
        response = self.client.post(url, {"card_id": self.card.pk, "solved": "True"})
        self.assertRedirects(response, url)
        self.card.refresh_from_db()
        self.assertEqual(self.card.box, 2)

    def test_create_deck_and_card_set_owner_and_deck(self):
        self.client.force_login(self.bob)
        self.client.post(reverse("deck-create"), {"name": "Verbs", "language": "es"})
        deck = Deck.objects.get(name="Verbs")
        self.assertEqual(deck.owner, self.bob)
        self.client.post(
            reverse("card-create", args=[deck.pk]),
            {"question": "comer", "answer": "manger", "example": "Vamos a comer.", "box": 1},
        )
        self.assertEqual(deck.cards.get(question="comer").example, "Vamos a comer.")

    def test_cannot_delete_another_users_card_or_deck(self):
        self.client.force_login(self.bob)
        self.client.post(reverse("card-delete", args=[self.deck.pk, self.card.pk]))
        self.client.post(reverse("card-delete", args=[self.bob_deck.pk, self.card.pk]))
        self.client.post(reverse("deck-delete", args=[self.deck.pk]))
        self.assertTrue(Card.objects.filter(pk=self.card.pk).exists())
        self.assertTrue(Deck.objects.filter(pk=self.deck.pk).exists())

    def test_owner_can_delete_card_then_deck(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("card-delete", args=[self.deck.pk, self.card.pk]))
        self.assertRedirects(response, reverse("card-list", args=[self.deck.pk]))
        self.assertFalse(Card.objects.filter(pk=self.card.pk).exists())
        response = self.client.post(reverse("deck-delete", args=[self.deck.pk]), follow=True)
        self.assertFalse(Deck.objects.filter(pk=self.deck.pk).exists())
        self.assertContains(response, "Paquet « Alice EN » supprimé.")


class StudyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice", password="pw")
        self.deck = Deck.objects.create(name="Words", language="en", owner=self.user)
        self.client.force_login(self.user)
        self.url = reverse("study", args=[self.deck.pk])

    def add_card(self, question, answer, box=1, days=0):
        return Card.objects.create(
            deck=self.deck, question=question, answer=answer, box=box,
            due_date=timezone.localdate() + timedelta(days=days),
        )

    def test_only_due_cards_are_offered(self):
        due = self.add_card("hectic", "intense", box=3, days=-2)
        self.add_card("cradle", "berceau", box=2, days=1)
        response = self.client.get(self.url)
        self.assertEqual(list(response.context["object_list"]), [due])
        self.assertEqual(response.context["check_card"], due)

    def test_shows_next_review_when_nothing_due(self):
        later = self.add_card("cradle", "berceau", box=2, days=3)
        response = self.client.get(self.url)
        self.assertNotIn("check_card", response.context)
        self.assertEqual(response.context["next_due"], later.due_date)

    def test_box_view_only_shows_due_cards_of_that_box(self):
        due = self.add_card("hectic", "intense", box=2)
        self.add_card("cradle", "berceau", box=2, days=1)
        self.add_card("grave", "tombe", box=3)
        response = self.client.get(reverse("box", args=[self.deck.pk, 2]))
        self.assertEqual(list(response.context["object_list"]), [due])
        self.assertEqual(response.context["box_total"], 2)

    def test_known_card_leaves_todays_review(self):
        card = self.add_card("hectic", "intense")
        response = self.client.post(self.url, {"card_id": card.pk, "solved": "True"})
        self.assertRedirects(response, self.url)
        response = self.client.get(self.url)
        self.assertNotIn("check_card", response.context)

    def test_reverse_direction_is_remembered(self):
        self.add_card("hectic", "intense")
        response = self.client.get(self.url + "?direction=reverse")
        self.assertTrue(response.context["reverse"])
        self.assertContains(response, '<h2 class="review-question">intense</h2>', html=True)
        response = self.client.get(self.url)
        self.assertTrue(response.context["reverse"])

    def test_answer_buttons_are_hidden_until_reveal(self):
        self.add_card("hectic", "intense")
        html = self.client.get(self.url).content.decode()
        details = html[html.index('<details class="answer'):html.index("</details>")]
        self.assertIn('data-solved="true"', details)
        self.assertIn('data-solved="false"', details)

    def test_type_mode_expects_the_hidden_side(self):
        self.add_card("hectic", "intense")
        response = self.client.get(self.url + "?answer_mode=type&direction=forward")
        self.assertContains(response, 'data-expected="intense"')
        response = self.client.get(self.url + "?direction=reverse")
        self.assertEqual(response.context["answer_mode"], "type")
        self.assertContains(response, 'data-expected="hectic"')

    def test_reveal_mode_has_no_typing_form(self):
        self.add_card("hectic", "intense")
        response = self.client.get(self.url)
        self.assertEqual(response.context["answer_mode"], "reveal")
        self.assertNotContains(response, 'class="type-answer"')

    def test_voice_picker_for_deck_language(self):
        self.deck.language = "es"
        self.deck.save()
        self.add_card("comer", "manger")
        for url in (self.url, reverse("card-list", args=[self.deck.pk])):
            html = self.client.get(url).content.decode()
            picker = html[html.index('<label class="voice-picker'):]
            self.assertIn('data-lang="es-ES" data-sample="comer"', picker[:300])

    def test_each_example_sentence_can_be_heard(self):
        card = self.add_card("a hatred", "une haine")
        card.example = "his hatred of injustice ; she looked at him with hatred"
        card.save()
        for url in (self.url, reverse("card-list", args=[self.deck.pk])):
            html = self.client.get(url).content.decode()
            self.assertIn('data-speak="his hatred of injustice"', html)
            self.assertIn('data-speak="she looked at him with hatred"', html)
            self.assertNotIn('data-speak="his hatred of injustice ;', html)

    def test_speak_button_uses_deck_voice(self):
        self.add_card("hectic", "intense")
        response = self.client.get(reverse("card-list", args=[self.deck.pk]))
        self.assertContains(response, 'data-speak="hectic" data-lang="en-GB"')

    def test_unknown_direction_is_ignored(self):
        self.add_card("hectic", "intense")
        response = self.client.get(self.url + "?direction=bogus")
        self.assertEqual(response.context["direction"], "forward")
        self.assertFalse(response.context["reverse"])


class CardListTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice", password="pw")
        self.deck = Deck.objects.create(name="Words", language="en", owner=self.user)
        self.client.force_login(self.user)
        self.url = reverse("card-list", args=[self.deck.pk])

    def test_search_matches_question_answer_and_example(self):
        Card.objects.create(deck=self.deck, question="Hectic", answer="Intense")
        Card.objects.create(deck=self.deck, question="Grave", answer="Tombe")
        Card.objects.create(deck=self.deck, question="Fancy", answer="Chic", example="A hectic day")
        response = self.client.get(self.url, {"q": "hectic"})
        self.assertEqual(
            sorted(card.question for card in response.context["card_list"]), ["Fancy", "Hectic"]
        )
        response = self.client.get(self.url, {"q": "tombe"})
        self.assertEqual([card.question for card in response.context["card_list"]], ["Grave"])

    def test_list_is_paginated_and_keeps_search(self):
        Card.objects.bulk_create(
            Card(deck=self.deck, question=f"word {n}", answer="mot") for n in range(30)
        )
        response = self.client.get(self.url, {"q": "word"})
        self.assertEqual(len(response.context["card_list"]), 25)
        self.assertContains(response, "?q=word&amp;page=2")
        response = self.client.get(self.url, {"q": "word", "page": 2})
        self.assertEqual(len(response.context["card_list"]), 5)


class StatsViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.deck = Deck.objects.create(name="Words", language="en", owner=self.alice)
        bob_deck = Deck.objects.create(name="Bob", language="es", owner=self.bob)
        now = timezone.now()
        for days_ago, solved in [(0, True), (0, False), (1, True), (2, True), (5, True)]:
            Review.objects.create(
                deck=self.deck, solved=solved, reviewed_at=now - timedelta(days=days_ago)
            )
        Review.objects.create(deck=bob_deck, solved=False, reviewed_at=now)
        Card.objects.create(deck=self.deck, question="q", answer="a", box=NUM_BOXES)

    def test_stats_only_count_own_reviews(self):
        self.client.force_login(self.alice)
        context = self.client.get(reverse("stats")).context
        self.assertEqual(context["streak"], 3)
        self.assertEqual(context["recent_total"], 5)
        self.assertEqual(context["success_rate"], 80)
        self.assertEqual(context["mastered"], 1)
        self.assertEqual(context["daily"][-1], {
            "date": timezone.localdate(), "total": 2, "solved": 1, "height": 100, "is_today": True,
        })
        self.assertEqual(context["decks"][0].box_counts, [0, 0, 0, 0, 1])

    def test_new_user_sees_empty_stats(self):
        self.client.force_login(self.bob)
        self.bob.decks.all().delete()
        response = self.client.get(reverse("stats"))
        self.assertEqual(response.context["success_rate"], None)
        self.assertContains(response, "Aucune révision ces 14 derniers jours.")

    def test_deck_list_shows_streak(self):
        self.client.force_login(self.alice)
        self.assertContains(self.client.get(reverse("deck-list")), "<strong>3 jours</strong>", html=True)

    def test_stats_require_login(self):
        self.assertEqual(self.client.get(reverse("stats")).status_code, 302)


class ImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice", password="pw")
        self.deck = Deck.objects.create(name="Words", language="en", owner=self.user)
        self.client.force_login(self.user)
        self.url = reverse("card-import", args=[self.deck.pk])

    def upload(self, content, encoding="utf-8"):
        csv_file = SimpleUploadedFile("cards.csv", content.encode(encoding), "text/csv")
        return self.client.post(self.url, {"csv_file": csv_file}, follow=True)

    def cards(self):
        return list(self.deck.cards.order_by("pk").values_list("question", "answer", "box"))

    def test_semicolon_file_with_header(self):
        self.upload("question;réponse\nHectic;Intense\nTo sprinkle;Saupoudrer\n")
        self.assertEqual(self.cards(), [("Hectic", "Intense", 1), ("To sprinkle", "Saupoudrer", 1)])

    def test_optional_example_column(self):
        self.upload("Hectic;Intense;It's been a hectic week.\nGrave;Tombe\n")
        self.assertEqual(
            list(self.deck.cards.order_by("pk").values_list("example", flat=True)),
            ["It's been a hectic week.", ""],
        )

    def test_comma_file_with_quotes_and_blank_lines(self):
        self.upload('Fancy,Sophistiqué\n\n"To jiggle","Se trémousser, gigoter"\n')
        self.assertEqual(self.cards(), [("Fancy", "Sophistiqué", 1),
                                        ("To jiggle", "Se trémousser, gigoter", 1)])

    def test_excel_cp1252_file(self):
        self.upload("Cradle;Berceau\r\nUndeniable;Indéniable\r\n", encoding="cp1252")
        self.assertEqual(self.cards()[1], ("Undeniable", "Indéniable", 1))

    def test_imported_cards_are_due_today(self):
        self.upload("Hectic;Intense\n")
        self.assertTrue(self.deck.cards.get().is_due)

    def test_existing_and_repeated_questions_are_skipped(self):
        Card.objects.create(deck=self.deck, question="Hectic", answer="Intense")
        response = self.upload("Hectic;Mouvementé\nGrave;Tombe\nGrave;Tombe\n")
        self.assertEqual(self.deck.cards.count(), 2)
        self.assertContains(response, "1 carte importée. 2 ignorées (déjà présentes).")

    def test_invalid_line_imports_nothing(self):
        response = self.upload("Hectic;Intense\nGrave\n")
        self.assertEqual(self.deck.cards.count(), 0)
        self.assertContains(response, "Ligne 2 : il faut une question et une réponse.")

    def test_too_long_field_is_rejected(self):
        response = self.upload("Hectic;" + "x" * 201 + ";" + "y" * 501 + "\nGrave;Tombe;" + "z" * 500)
        self.assertEqual(self.deck.cards.count(), 0)
        self.assertContains(
            response,
            "Ligne 1 : trop long pour réponse (200 caractères max.), exemple (500 caractères max.).",
        )
        self.assertNotContains(response, "Ligne 2")

    def test_empty_file_is_rejected(self):
        response = self.upload("question;réponse\n")
        self.assertContains(response, "Le fichier ne contient aucune carte.")


def make_collection(note_types, modern):
    """Build an Anki collection database; note_types maps (id, name, fields) to notes."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as db_file:
        path = db_file.name
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, mid INTEGER, flds TEXT)")
    if modern:
        # Like Anki, use its custom collation, unknown to plain SQLite
        connection.create_collation("unicase", anki.compare_unicase)
        connection.execute("CREATE TABLE notetypes (id INTEGER PRIMARY KEY, name TEXT COLLATE unicase)")
        connection.execute(
            "CREATE TABLE fields (ntid INTEGER, ord INTEGER, name TEXT COLLATE unicase, "
            "PRIMARY KEY (ntid, ord))"
        )
        connection.execute("CREATE UNIQUE INDEX idx_fields_name_ntid ON fields (name, ntid)")
    else:
        connection.execute("CREATE TABLE col (id INTEGER PRIMARY KEY, models TEXT)")
    models = {}
    for (ntid, name, fields), notes in note_types.items():
        if modern:
            connection.execute("INSERT INTO notetypes VALUES (?, ?)", (ntid, name))
            # Insert fields out of order: the reader must sort them
            for order, field in reversed(list(enumerate(fields))):
                connection.execute("INSERT INTO fields VALUES (?, ?, ?)", (ntid, order, field))
        else:
            models[str(ntid)] = {
                "name": name,
                "flds": [{"name": field, "ord": order} for order, field in enumerate(fields)],
            }
        for note in notes:
            connection.execute(
                "INSERT INTO notes (mid, flds) VALUES (?, ?)", (ntid, "\x1f".join(note))
            )
    if not modern:
        connection.execute("INSERT INTO col VALUES (1, ?)", (json.dumps(models),))
    connection.commit()
    connection.close()
    with open(path, "rb") as db_file:
        data = db_file.read()
    os.unlink(path)
    return data


def make_apkg(note_types, modern=False, name="deck.apkg"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if modern:
            archive.writestr(
                "collection.anki21b",
                zstandard.ZstdCompressor().compress(make_collection(note_types, modern=True)),
            )
            placeholder = {(1, "Basic", ("Front", "Back")): [
                ["Please update to the latest Anki version, then import the .colpkg/.apkg file again.", ""]
            ]}
            archive.writestr("collection.anki2", make_collection(placeholder, modern=False))
        else:
            archive.writestr("collection.anki2", make_collection(note_types, modern=False))
        archive.writestr("media", "{}")
    return SimpleUploadedFile(name, buffer.getvalue(), "application/octet-stream")


BASIC = (1001, "Basic", ("Front", "Back", "Example"))


class AnkiReaderTests(TestCase):
    def test_clean_field(self):
        self.assertEqual(anki.clean_field("<b>To</b>&nbsp;sprinkle [sound:a.mp3]"), "To sprinkle")
        self.assertEqual(anki.clean_field("{{c1::hola::greeting}} amigo"), "hola amigo")
        self.assertEqual(anki.clean_field("<div>uno</div><div>dos</div>"), "uno dos")
        self.assertEqual(anki.clean_field('<img src="cat.jpg">gato &amp; perro'), "gato & perro")

    def test_shorten(self):
        self.assertEqual(anki.shorten("short", 10), "short")
        self.assertEqual(anki.shorten("one example ; another one ; a third", 30), "one example ; another one…")
        self.assertEqual(anki.shorten("a sentence without separators at all", 20), "a sentence without…")
        self.assertLessEqual(len(anki.shorten("x" * 600, 500)), 500)

    def test_suggest_mapping_by_field_names(self):
        fields = ["Note ID", "LexiqueFR", "Front", "Back", "ExempleEN", "ExempleFR"]
        notes = [["1461616377470", "insulte", "a scum", "une pourriture", "the scum of the earth", ""]] * 3
        self.assertEqual(
            anki.suggest_mapping(fields, notes), {"question": 2, "answer": 3, "example": 4}
        )

    def test_suggest_mapping_skips_ids_and_empty_fields(self):
        fields = ["Id", "Vide", "Mot", "Traduction du mot"]
        notes = [["1", "", "comer", "manger"], ["2", "", "beber", "boire"]]
        self.assertEqual(
            anki.suggest_mapping(fields, notes), {"question": 2, "answer": 3, "example": None}
        )

    def test_numeric_fields(self):
        notes = [["12", "a", "3"], ["13", "b", ""], ["14", "c", "x"]]
        self.assertEqual(anki.numeric_fields(notes), {0})

    def test_legacy_package(self):
        note_types = anki.read_apkg(make_apkg({BASIC: [["Hectic", "<i>Intense</i>", ""]]}))
        self.assertEqual(note_types, [{
            "id": "1001", "name": "Basic", "fields": ["Front", "Back", "Example"],
            "notes": [["Hectic", "Intense", ""]],
        }])

    def test_modern_package_is_preferred_over_placeholder(self):
        note_types = anki.read_apkg(make_apkg({BASIC: [["Cradle", "Berceau", "A baby cradle"]]}, modern=True))
        self.assertEqual(note_types[0]["fields"], ["Front", "Back", "Example"])
        self.assertEqual(note_types[0]["notes"], [["Cradle", "Berceau", "A baby cradle"]])

    def test_missing_fields_are_padded(self):
        note_types = anki.read_apkg(make_apkg({BASIC: [["Grave", "Tombe"]]}))
        self.assertEqual(note_types[0]["notes"], [["Grave", "Tombe", ""]])

    def test_note_types_sorted_by_use(self):
        other = (2002, "Reverse", ("A", "B"))
        note_types = anki.read_apkg(make_apkg({
            BASIC: [["a", "b", ""]],
            other: [["c", "d"], ["e", "f"]],
            (3003, "Unused", ("X",)): [],
        }))
        self.assertEqual([nt["name"] for nt in note_types], ["Reverse", "Basic"])

    def test_placeholder_only_package_is_rejected(self):
        placeholder = {BASIC: [["Please update to the latest Anki version, then import.", "", ""]]}
        with self.assertRaisesMessage(anki.AnkiImportError, "réexportez-le depuis Anki"):
            anki.read_apkg(make_apkg(placeholder))

    def test_invalid_files_are_rejected(self):
        not_zip = SimpleUploadedFile("deck.apkg", b"not a zip")
        with self.assertRaisesMessage(anki.AnkiImportError, "pas un paquet Anki"):
            anki.read_apkg(not_zip)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("collection.anki2", b"garbage")
        with self.assertRaisesMessage(anki.AnkiImportError, "illisible"):
            anki.read_apkg(SimpleUploadedFile("deck.apkg", buffer.getvalue()))


class AnkiImportViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice", password="pw")
        self.deck = Deck.objects.create(name="Words", language="en", owner=self.user)
        self.client.force_login(self.user)
        self.upload_url = reverse("anki-upload", args=[self.deck.pk])
        self.map_url = reverse("anki-map", args=[self.deck.pk])

    def upload(self, apkg):
        return self.client.post(self.upload_url, {"apkg_file": apkg})

    def test_full_import_with_field_mapping(self):
        Card.objects.create(deck=self.deck, question="Hectic", answer="Intense")
        response = self.upload(make_apkg({BASIC: [
            ["Intense", "Hectic", "A hectic week"],
            ["Berceau", "Cradle", "A baby <b>cradle</b>"],
            ["", "Grave", ""],
            ["Tombe", "x" * 201, ""],
            ["Long", "Lengthy", "It goes on ; " * 50],
        ]}, name="english.apkg"))
        self.assertRedirects(response, self.map_url)

        response = self.client.get(self.map_url)
        self.assertContains(response, "english.apkg")
        self.assertContains(response, "<th>Example</th>", html=True)

        # Back is the English word here: use it as the question
        response = self.client.post(
            self.map_url, {"note_type": "1001", "question": 1, "answer": 0, "example": 2}, follow=True
        )
        self.assertRedirects(response, reverse("card-list", args=[self.deck.pk]))
        self.assertEqual(
            list(self.deck.cards.order_by("pk").values_list("question", "answer", "example", "box")),
            [("Hectic", "Intense", "", 1), ("Cradle", "Berceau", "A baby cradle", 1)]
            + [("Lengthy", "Long", anki.shorten("It goes on ; " * 50, 500), 1)],
        )
        self.assertTrue(self.deck.cards.get(question="Lengthy").example.endswith("on…"))
        self.assertContains(
            response,
            "2 cartes importées. 1 ignorée (déjà présente). 1 ignorée (question ou réponse vide). "
            "1 ignorée (trop longue).",
        )
        self.assertNotIn("anki_import", self.client.session)

    def test_fields_are_preselected_and_ids_refused(self):
        note_type = (1001, "Vocab", ("Note ID", "LexiqueFR", "Front", "Back", "ExempleEN"))
        self.upload(make_apkg({note_type: [
            ["1461656318080", "université", "a university", "une université", "She went to university."],
            ["1461656318090", "université", "a campus", "un campus", ""],
        ]}))
        form = self.client.get(self.map_url).context["form"]
        self.assertEqual(
            [form.initial[role] for role in ("question", "answer", "example")], [2, 3, 4]
        )
        response = self.client.post(self.map_url, {"note_type": "1001", "question": 0, "answer": 1})
        self.assertContains(response, "Le champ « Note ID » ne contient presque que des nombres")
        self.assertEqual(self.deck.cards.count(), 0)

    def test_example_is_optional(self):
        self.upload(make_apkg({BASIC: [["Cradle", "Berceau", "A cradle"]]}))
        self.client.post(self.map_url, {"note_type": "1001", "question": 0, "answer": 1, "example": ""})
        self.assertEqual(self.deck.cards.get().example, "")

    def test_same_field_twice_is_rejected(self):
        self.upload(make_apkg({BASIC: [["Cradle", "Berceau", ""]]}))
        response = self.client.post(self.map_url, {"note_type": "1001", "question": 0, "answer": 0})
        self.assertContains(response, "Choisissez un champ différent pour chaque rôle.")
        self.assertEqual(self.deck.cards.count(), 0)

    def test_choose_another_note_type(self):
        other = (2002, "Vocab", ("Word", "Meaning"))
        self.upload(make_apkg({BASIC: [["a", "b", ""], ["c", "d", ""]], other: [["comer", "manger"]]}))
        response = self.client.get(self.map_url)
        self.assertEqual(response.context["note_type"]["name"], "Basic")
        response = self.client.get(self.map_url, {"note_type": "2002"})
        self.assertContains(response, "Word — « comer »")
        self.client.post(self.map_url, {"note_type": "2002", "question": 0, "answer": 1})
        self.assertEqual(list(self.deck.cards.values_list("question", flat=True)), ["comer"])

    def test_upload_errors_are_shown(self):
        response = self.upload(SimpleUploadedFile("deck.txt", b"Hectic;Intense"))
        self.assertContains(response, "Choisissez un fichier .apkg.")
        response = self.upload(SimpleUploadedFile("deck.apkg", b"not a zip"))
        self.assertContains(response, "pas un paquet Anki")

    def test_mapping_without_upload_goes_back_to_upload(self):
        self.assertRedirects(self.client.get(self.map_url), self.upload_url)

    def test_pending_import_is_tied_to_its_deck(self):
        self.upload(make_apkg({BASIC: [["Cradle", "Berceau", ""]]}))
        other_deck = Deck.objects.create(name="Other", language="en", owner=self.user)
        other_map_url = reverse("anki-map", args=[other_deck.pk])
        self.assertRedirects(
            self.client.get(other_map_url), reverse("anki-upload", args=[other_deck.pk])
        )


class SignUpTests(TestCase):
    def test_signup_logs_user_in(self):
        response = self.client.post(reverse("signup"), {
            "username": "carol",
            "password1": "a-Strong-pass-42",
            "password2": "a-Strong-pass-42",
        })
        self.assertRedirects(response, reverse("deck-list"))
        self.assertEqual(int(self.client.session["_auth_user_id"]),
                         get_user_model().objects.get(username="carol").pk)
