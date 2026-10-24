# Flashcards

Application web de flashcards pour apprendre le vocabulaire de langues étrangères (anglais, espagnol), écrite avec [Django](https://www.djangoproject.com/).

Elle repose sur le **système de Leitner** : chaque carte avance d'une boîte quand on la connaît et revient à la première quand on se trompe. Plus une carte est dans une boîte élevée, plus sa prochaine révision est espacée.

Le projet est parti du tutoriel [Real Python « Build a Flashcards App With Django »](https://realpython.com/django-flashcards-app/), puis a été enrichi.

## Fonctionnalités

- **Comptes utilisateurs** : inscription, connexion ; chacun ne voit que ses propres cartes.
- **Paquets par langue** : regroupez vos cartes en paquets (« Anglais – verbes », « Espagnol – cuisine »…).
- **Révisions espacées** : seules les cartes dues aujourd'hui sont proposées.
- **Deux sens de révision** : question → réponse, réponse → question, ou mélangé.
- **Deux modes de réponse** :
  - **révéler** la réponse puis dire si on la savait ;
  - **taper** la réponse. La comparaison ignore les majuscules et la ponctuation, et signale les fautes d'accent.
- **Phrase d'exemple** facultative sur chaque carte.
- **Prononciation** 🔊 par la synthèse vocale du navigateur, avec une voix anglaise ou espagnole selon le paquet.
- **Import CSV** pour ajouter beaucoup de cartes d'un coup.
- **Statistiques** :
  - série de jours de révision d'affilée 🔥 ;
  - taux de réussite ;
  - graphique des 14 derniers jours ;
  - progression par paquet.
- **Recherche** dans les cartes et **pagination**.
- **Raccourcis clavier** pour réviser vite, et affichage adapté au mobile.
- Interface en français.

## Prérequis

- **Python 3.12 ou plus récent** (exigé par Django 6.1)
- **git**

## Installation

### 1. Récupérer le projet

```bash
git clone https://github.com/arribo44/Flashcards.git
cd Flashcards
```

### 2. Créer un environnement virtuel et installer les dépendances

Sous Linux ou macOS :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Sous Windows (PowerShell) :

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Les commandes `python …` des étapes suivantes supposent que l'environnement virtuel est activé.

### 3. Configurer l'application

La configuration sensible n'est pas dans le code : elle est lue dans un fichier `.env` à la racine du projet. Ce fichier n'est **jamais** envoyé sur GitHub, car il est listé dans `.gitignore`.

Copiez le modèle :

```bash
cp .env.example .env
```

Générez une clé secrète :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Puis ouvrez `.env` et complétez-le :

```ini
DJANGO_SECRET_KEY=collez-ici-la-clé-générée
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
```

| Variable | Rôle | Valeur par défaut |
|---|---|---|
| `DJANGO_SECRET_KEY` | Clé secrète de Django (sessions, jetons CSRF…). **Obligatoire** : l'application refuse de démarrer sans elle. | aucune |
| `DJANGO_DEBUG` | `True` pour développer en local (pages d'erreur détaillées). À laisser à `False` en production. | `False` |
| `DJANGO_ALLOWED_HOSTS` | Noms de domaine autorisés, séparés par des virgules. | `localhost,127.0.0.1` |

### 4. Créer la base de données

```bash
python manage.py migrate
```

La base SQLite `db.sqlite3` est créée à la racine du projet. Elle reste sur votre machine et n'est pas versionnée.

### 5. (Facultatif) Créer un administrateur

```bash
python manage.py createsuperuser
```

Ce compte donne accès à l'interface d'administration (`/admin/`). Pour simplement utiliser l'application, un compte créé depuis la page d'inscription suffit.

### 6. Lancer l'application

```bash
python manage.py runserver
```

Ouvrez <http://127.0.0.1:8000/>, créez un compte, et c'est parti.

## Utilisation

### Créer des cartes

1. Sur la page **Mes paquets**, cliquez sur **✨ Nouveau paquet**. Donnez-lui un nom et choisissez sa langue.
2. Dans le paquet, ajoutez des cartes une par une avec **✨ Nouvelle carte**, ou importez un fichier avec **📥 Importer un CSV**.

Les champs d'une carte :

- la **question**, dans la langue étudiée, par exemple *Hectic*. C'est elle que lit le bouton 🔊 ;
- la **réponse**, en français, par exemple *Intense* ;
- l'**exemple**, facultatif, par exemple *It's been a hectic week.*

### Importer un fichier CSV

Le fichier contient une carte par ligne, avec deux ou trois colonnes : question, réponse et, si vous le voulez, un exemple.

```csv
question;réponse;exemple
Hectic;Intense;It's been a hectic week.
To sprinkle;Saupoudrer;
Cradle;Berceau;
```

- **Séparateur** : virgule, point-virgule ou tabulation. Il est détecté automatiquement.
- **Encodage** : UTF-8, ou le format « CSV (séparateur : point-virgule) » d'Excel sous Windows.
- **En-tête** : une première ligne commençant par `question` est ignorée.
- **Doublons** : les questions déjà présentes dans le paquet sont ignorées.
- **Tout ou rien** : si une ligne est invalide (réponse manquante, texte trop long), **rien n'est importé** et les lignes en erreur sont indiquées.
- **Limites** : 1 Mo par fichier, 100 caractères pour la question et la réponse, 200 pour l'exemple.

### Réviser

Cliquez sur **🎯 Réviser** pour lancer la révision du jour. Elle pioche parmi toutes les cartes dues du paquet. Chaque boîte peut aussi être révisée séparément depuis la barre de navigation, où `🗃 Boîte 2 3/5` signifie 3 cartes à réviser sur 5 dans la boîte.

En haut de la page de révision, vous choisissez :

- **le sens** : Question → Réponse, Réponse → Question, ou Mélangé ;
- **le mode** : Révéler la réponse, ou Taper la réponse.

Ces choix sont mémorisés pendant votre session.

En mode saisie, plusieurs réponses séparées par `,`, `;` ou `/` sont acceptées. Par exemple, « Se trémousser, gigoter » accepte les deux. Le bouton correspondant au verdict est présélectionné : <kbd>Entrée</kbd> le valide, mais vous pouvez cliquer sur l'autre si vous estimez que votre réponse était juste.

Raccourcis clavier :

| Touche | Action |
|---|---|
| <kbd>Espace</kbd> | Afficher la réponse |
| <kbd>→</kbd> | Je sais |
| <kbd>←</kbd> | Je ne sais pas |
| <kbd>P</kbd> | Écouter la prononciation |

### Le rythme des révisions

| La carte arrive en… | Boîte 1 | Boîte 2 | Boîte 3 | Boîte 4 | Boîte 5 |
|---|---|---|---|---|---|
| Prochaine révision | le jour même | 1 jour | 3 jours | 7 jours | 14 jours |

- **Si vous savez la réponse**, la carte monte d'une boîte. En boîte 5, elle y reste.
- **Si vous ne la savez pas**, elle retourne en boîte 1 et revient dans la même séance.
- **Nouvelles cartes** : elles commencent en boîte 1, à réviser tout de suite.
- **Réglage** : les délais se modifient dans `REVIEW_INTERVALS`, dans [`cards/models.py`](cards/models.py).

La progression est commune aux deux sens de révision : une carte ratée en sens inverse repart en boîte 1.

### Statistiques

La page **📊 Statistiques** affiche :

- la série de jours de révision d'affilée et votre record ;
- le nombre de cartes à réviser aujourd'hui ;
- le taux de réussite sur 30 jours ;
- les cartes maîtrisées (en boîte 5) ;
- un graphique des révisions des 14 derniers jours, avec le détail en tableau ;
- la répartition des cartes par boîte pour chaque paquet.

Chaque réponse est enregistrée dans un historique qui est conservé même si la carte est supprimée.

## Développement

### Lancer les tests

```bash
python manage.py test cards
```

Les tests couvrent :

- la logique de Leitner et les échéances ;
- le cloisonnement entre utilisateurs ;
- la révision et ses deux sens ;
- l'import CSV ;
- les statistiques, la recherche et la pagination.

### Structure du projet

```text
flashcards/            Configuration du projet Django (settings, URLs)
cards/                 L'application
├── models.py          Paquets (Deck), cartes (Card), historique (Review)
├── views.py           Pages : paquets, cartes, révision, import, statistiques
├── forms.py           Validation des réponses et lecture des fichiers CSV
├── stats.py           Calcul des séries et des révisions par jour
├── urls.py            Routes de l'application
├── admin.py           Interface d'administration
├── tests.py           Tests automatisés
├── templates/         Gabarits HTML
├── static/cards/      JavaScript (révision, synthèse vocale) et feuille de style
└── migrations/        Évolutions du schéma de la base
requirements.txt       Dépendances Python, versions figées
.env.example           Modèle de configuration à copier en .env
```

### Ajouter une langue

1. Ajoutez la langue dans `Deck.Language` et sa voix dans `Deck.SPEECH_LANGS`, dans [`cards/models.py`](cards/models.py) :

   ```python
   GERMAN = "de", "Allemand"
   ```

   ```python
   Language.GERMAN: "de-DE"
   ```

2. Créez et appliquez la migration :

   ```bash
   python manage.py makemigrations cards
   python manage.py migrate
   ```

### Envoyer ses modifications sur GitHub

```bash
git status                       # voir ce qui a changé
git add -A                       # préparer tous les changements
git commit -m "Ce que j'ai fait" # enregistrer une version
git push                         # envoyer sur GitHub
```

Pour récupérer les mises à jour sur une autre machine :

```bash
git pull
pip install -r requirements.txt  # si les dépendances ont changé
python manage.py migrate         # si le modèle de données a changé
```

Si vous installez une nouvelle dépendance, mettez à jour la liste avec `pip freeze > requirements.txt` avant de commiter.

## Mise en production

L'application est prête pour un usage local. Avant de la mettre en ligne :

- mettez `DJANGO_DEBUG=False` et indiquez votre domaine dans `DJANGO_ALLOWED_HOSTS` ;
- utilisez une clé secrète propre à ce serveur ;
- rassemblez les fichiers statiques. Il faut pour cela définir `STATIC_ROOT` dans `flashcards/settings.py`, puis lancer `python manage.py collectstatic` ;
- servez l'application derrière un serveur WSGI (Gunicorn, uWSGI…) plutôt qu'avec `runserver` ;
- activez HTTPS. `python manage.py check --deploy` liste les réglages restants : `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` ;
- pour plusieurs utilisateurs, préférez PostgreSQL à SQLite. Cela corrige aussi la recherche, qui ne tient pas compte des majuscules accentuées sous SQLite.

## Licence

Ce projet est distribué sous licence MIT : voir le fichier [LICENSE](LICENSE).

## Crédits

- Tutoriel de départ : [Real Python](https://realpython.com/django-flashcards-app/)
- Feuille de style : [Simple.css](https://simplecss.org/), licence MIT, incluse dans `cards/static/cards/`
