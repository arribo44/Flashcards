from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Card, Deck, NUM_BOXES


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
            reverse("deck-update", args=[self.deck.pk]),
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
            {"question": "comer", "answer": "manger", "box": 1},
        )
        self.assertTrue(deck.cards.filter(question="comer").exists())


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
