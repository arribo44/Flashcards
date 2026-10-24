from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import stats
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
        self.assertContains(response, "<h4>intense</h4>", html=True)
        response = self.client.get(self.url)
        self.assertTrue(response.context["reverse"])

    def test_answer_buttons_are_hidden_until_reveal(self):
        self.add_card("hectic", "intense")
        html = self.client.get(self.url).content.decode()
        details = html[html.index('<details class="answer">'):html.index("</details>")]
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
        response = self.upload("Hectic;" + "x" * 101 + ";" + "y" * 201 + "\nGrave;Tombe;" + "z" * 200)
        self.assertEqual(self.deck.cards.count(), 0)
        self.assertContains(
            response,
            "Ligne 1 : trop long pour réponse (100 caractères max.), exemple (200 caractères max.).",
        )
        self.assertNotContains(response, "Ligne 2")

    def test_empty_file_is_rejected(self):
        response = self.upload("question;réponse\n")
        self.assertContains(response, "Le fichier ne contient aucune carte.")


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
