"""Fixtures communes : intégrations de custom_components/ et recorder (dépendance de l'intégration).

``recorder_mock`` doit être demandé avant ``hass`` : d'où sa place dans ce fixture automatique.
"""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Toutes les fonctions de test voient custom_components/tarifenergie et un recorder en mémoire."""
    return
