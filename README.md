# Taskify HR – API (back end)

API REST de **Taskify HR** : pointage géolocalisé et gestion des congés pour les PME.
Elle remplace les services simulés de l'application mobile .NET MAUI
([dépôt du front end](https://github.com/Beautrel/TaskifyHR)).

**Technologies :** Python, Django 5.2 LTS, Django REST Framework, JWT (SimpleJWT),
PostgreSQL (SQLite par défaut en développement), documentation OpenAPI (Swagger).

## Lancer l'API

Prérequis : Python 3.10 ou plus.

```bash
python -m venv .venv
source .venv/Scripts/activate        # Git Bash sous Windows (Linux/macOS : .venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo           # comptes et demandes de démonstration
python manage.py runserver 0.0.0.0:8000
```

- Documentation interactive : <http://localhost:8000/api/docs/>
- Administration : `python manage.py createsuperuser`, puis <http://localhost:8000/admin/>

### Comptes de démonstration (mot de passe commun : `Taskify2026!`)

| Compte | Rôle |
|---|---|
| `sophie.bernard@taskify.fr` | Manager |
| `lea.martin@taskify.fr` | Employée (équipe de Sophie) |
| `hugo.petit@taskify.fr` | Employé (équipe de Sophie) |

Les données sont identiques à celles des écrans simulés de l'application (solde de Léa : 12 jours, etc.).
`python manage.py seed_demo --reset` remet les données de démonstration à zéro.

## Utiliser l'API depuis le téléphone

1. PC et téléphone sur le **même Wi-Fi**.
2. Lancer `runserver 0.0.0.0:8000` et relever l'adresse IP du PC (`ipconfig`).
3. Autoriser le port 8000 dans le pare-feu Windows (réseau privé).
4. L'application utilise `http://<IP-du-PC>:8000/api/`. Émulateur Android : `http://10.0.2.2:8000/api/`.

## Endpoints

Toutes les routes (sauf `auth/*`) demandent l'en-tête `Authorization: Bearer <access>`.

| Méthode | Route | Rôle | Description |
|---|---|---|---|
| POST | `/api/auth/register/` | public | Création de compte employé |
| POST | `/api/auth/login/` | public | Connexion par e-mail → `access`, `refresh`, `user` |
| POST | `/api/auth/refresh/` | public | Nouveau `access` à partir du `refresh` |
| GET / PATCH | `/api/me/` | connecté | Profil ; seul `phone` est modifiable |
| GET | `/api/attendance/today/` | connecté | Pointage du jour (`before_entry`, `in_progress`, `done`) |
| POST | `/api/attendance/clock-in/` | connecté | Entrée, avec `latitude` et `longitude` |
| POST | `/api/attendance/clock-out/` | connecté | Sortie, avec `latitude` et `longitude` |
| GET | `/api/leave/balance/` | connecté | Solde de congés payés |
| GET / POST | `/api/leave/requests/` | connecté | Mes demandes / nouvelle demande |
| GET | `/api/manager/approvals/` | manager | Demandes en attente de son équipe |
| POST | `/api/manager/requests/<id>/approve/` | manager | Approuver |
| POST | `/api/manager/requests/<id>/refuse/` | manager | Refuser, avec `reason` obligatoire |
| GET | `/api/manager/report/?month=AAAA-MM` | manager | Aperçu de l'export mensuel |
| GET | `/api/manager/report/export/?month=AAAA-MM&format=pdf\|csv` | manager | Téléchargement du fichier |

Exemple :

```bash
curl -X POST http://localhost:8000/api/auth/login/ -H "Content-Type: application/json" \
     -d '{"email":"lea.martin@taskify.fr","password":"Taskify2026!"}'

curl -X POST http://localhost:8000/api/attendance/clock-in/ \
     -H "Authorization: Bearer <access>" -H "Content-Type: application/json" \
     -d '{"latitude":4.0511,"longitude":9.7679}'
```

### Format des erreurs

- Validation (400) : `{"champ": ["message en français"]}`, ou `{"non_field_errors": ["..."]}`.
- Règle de gestion (409) : `{"detail": "..."}`, par exemple `Cette demande a déjà été traitée.`
- Pointage : `{"code": "out_of_zone" | "position_required" | "already_clocked_in" | "no_clock_in" | "already_clocked_out", "detail": "..."}`.
- 401 : jeton absent ou expiré ; 403 : rôle insuffisant ; 404 : demande hors de l'équipe du manager.

## Règles métier (appliquées côté serveur)

- **Congés** : début strictement futur, fin ≥ début, uniquement des **jours ouvrés** (lundi à vendredi),
  pas de chevauchement avec une demande non refusée, solde suffisant pour les congés payés.
  Les jours sont **calculés par le serveur**.
- **Solde** : 20 jours par période (1er juin au 31 mai). Les jours ne sont déduits **qu'à l'approbation** ;
  le solde est **revérifié au moment de la décision**.
- **Manager** : ne voit et ne décide que pour **son équipe** (`manager` de l'employé). Un refus exige un **motif**.
- **Pointage** : une entrée et une sortie par jour, **heure du serveur** (fuseau Europe/Paris), position
  obligatoire et **dans le rayon** du lieu de travail (200 m par défaut).
- **Compte** : mot de passe de 12 caractères avec une majuscule et un chiffre ; matricule au format `TF-042`,
  unique ; e-mail unique.

## Sécurité

- Mots de passe hachés par Django (PBKDF2) ; jamais renvoyés par l'API.
- Jeton d'accès JWT de 30 minutes, jeton de rafraîchissement de 7 jours.
- Limitation de débit sur la connexion et l'inscription (20 requêtes par minute et par adresse).
- Contrôle d'accès par rôle (RBAC) testé : un employé reçoit 403 sur toutes les routes manager.
- En production : définir `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, utiliser HTTPS.

## Tests

```bash
python manage.py test
```

43 tests : validation d'inscription, authentification, profil, règles des congés, parcours manager,
RBAC, pointage, export CSV/PDF. La date du jour est fixée dans les tests, ils ne dépendent pas de la date d'exécution.

## PostgreSQL (optionnel)

```bash
docker compose up -d
export POSTGRES_DB=taskify POSTGRES_USER=taskify POSTGRES_PASSWORD=taskify POSTGRES_HOST=localhost
python manage.py migrate && python manage.py seed_demo
```

## Limites connues

- Les jours fériés ne sont pas exclus du calcul des jours ouvrés.
- Une demande à cheval sur deux périodes de congés est rattachée à la période de son premier jour.
- Pas de notification (e-mail ou push) à l'employé après une décision.
- Un seul lieu de travail utilisé pour la vérification de zone.
- Pas encore déployé en ligne : l'API tourne sur la machine de développement.
