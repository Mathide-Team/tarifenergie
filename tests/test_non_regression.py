"""Non-régression des coûts (#359) : chaque offre-option coûte exactement la référence.

La référence ``tests/donnees/reference_couts.json`` a été calculée avec le moteur
d'avant le découpage des offres en offres-options (#343). Une différence signale soit
une régression du moteur, soit un changement de grille : dans ce second cas, regénérer
la référence volontairement (voir ``tests/reference_couts.py``) et justifier le diff
dans la PR.
"""

import json

import pytest

from .reference_couts import FICHIER, calculer

REFERENCE = json.loads(FICHIER.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def actuel():
    return calculer()


def test_memes_scenarios(actuel):
    assert sorted(actuel) == sorted(REFERENCE)


@pytest.mark.parametrize("scenario", sorted(REFERENCE))
def test_couts_identiques(actuel, scenario):
    """Mêmes offres-options calculées, mêmes montants exacts, mêmes raisons d'indisponibilité."""
    attendu, obtenu = REFERENCE[scenario], actuel[scenario]
    assert sorted(obtenu["couts"]) == sorted(attendu["couts"])
    assert obtenu["indisponibles"] == attendu["indisponibles"]
    for cle, cout in attendu["couts"].items():
        assert obtenu["couts"][cle] == cout, f"{scenario} : {cle}"
