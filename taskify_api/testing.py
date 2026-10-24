"""Aides pour les tests : on fixe « aujourd'hui » au lundi 12 octobre 2026
pour que les résultats ne dépendent jamais de la date d'exécution."""
from datetime import date, timedelta
from unittest.mock import patch

FIXED_TODAY = date(2026, 10, 12)  # un lundi, dans la période de congés juin 2026 - mai 2027


def freeze_today(testcase):
    patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
    patcher.start()
    testcase.addCleanup(patcher.stop)


def monday(weeks_ahead: int) -> date:
    """Lundi situé `weeks_ahead` semaines après le lundi fixé (toujours dans le futur si > 0)."""
    return FIXED_TODAY + timedelta(weeks=weeks_ahead)
