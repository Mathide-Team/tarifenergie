"""Coûts de référence pour les tests de non-régression (#359).

Ce module calcule, pour des profils de consommation fixes et déterministes, le coût
de chaque offre-option (TRV et offres de marché) et l'écrit dans
``tests/donnees/reference_couts.json``. Le test ``test_non_regression.py`` recalcule
les mêmes coûts avec le code courant et exige un résultat identique, au centime et
au-delà (montants ``Decimal`` exacts).

La référence initiale a été produite **avec le moteur d'avant le découpage** des
fichiers d'offres par offre-option (#343) : elle prouve que le découpage ne change
aucun coût. Les anciennes clés ``<offre>:<option>`` y sont écrites sous leur nouveau
nom ``<offre>_<option>``.

Regénérer volontairement (après un changement de grille assumé) :

    uv run -p 3.13 --only-group test python -m tests.reference_couts
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from custom_components.tarifenergie.calcul import PlagesHC, comparer
from custom_components.tarifenergie.const import OPTIONS
from custom_components.tarifenergie.modele import Grilles
from custom_components.tarifenergie.offres import grilles_offres, lire_offres
from custom_components.tarifenergie.tempo import estimer, jours_utiles, lire_couleurs

FICHIER = Path(__file__).parent / "donnees" / "reference_couts.json"

# Profils de 12 mois, heure locale :
# - « historique » : TRV sur deux révisions CRE (1er février, 1er août) ; les offres de
#   marché, dont les grilles datent d'août à octobre 2026, y sont indisponibles avec la raison ;
# - « recent » : à partir du 16/10/2026 (grille la plus récente des offres livrées),
#   toutes les offres-options calculables.
PROFILS = {
    "historique": datetime(2025, 10, 16),
    "recent": datetime(2026, 10, 16),
}
# Plages d'heures creuses : demi-heures (prorata des minutes) et plages d'après-midi.
PLAGES = ("23:30-07:30", "02:00-07:00, 13:00-16:00")
PUISSANCES = (3, 6, 9, 12, 36)
HEURES = 365 * 24
# Tempo (#340) : historique réel des couleurs **figé** à cette date, pour que la mise à jour
# quotidienne du fichier de couleurs ne change pas la référence. Au-delà (profil « recent »),
# les couleurs sont estimées selon les règles Tempo.
COULEURS_JUSQUAU = date(2026, 10, 15)


def profil(debut: datetime) -> list[tuple[datetime, float]]:
    """Consommation horaire déterministe : fond variable, pointe de nuit et d'après-midi."""
    conso = []
    for i in range(HEURES):
        instant = debut + timedelta(hours=i)
        jour, heure = divmod(i, 24)
        kwh = 0.25 + 0.15 * ((heure * 7 + jour * 5) % 13) / 12
        if heure in (2, 3):
            kwh += 1.5  # ballon d'eau chaude
        if heure == 14:
            kwh += 0.8
        conso.append((instant, round(kwh, 3)))
    return conso


def grilles() -> dict[str, Grilles]:
    """Toutes les offres-options, sous leur clé de comparaison actuelle."""
    toutes = {option: Grilles.charger(option) for option in OPTIONS}
    toutes.update({cle.replace(":", "_"): g for cle, g in grilles_offres(lire_offres()).items()})
    return toutes


def calculer() -> dict[str, object]:
    resultats: dict[str, object] = {}
    toutes = grilles()
    historique = {j: c for j, c in lire_couleurs().items() if j <= COULEURS_JUSQUAU}
    for nom, debut in PROFILS.items():
        conso = profil(debut)
        couleurs = estimer(historique, jours_utiles(d.date() for d, _ in conso))
        for texte in PLAGES:
            plages = PlagesHC.lire(texte)
            for puissance in PUISSANCES:
                comp = comparer(toutes, puissance, conso, plages, "base", couleurs=couleurs)
                resultats[f"{nom}|{texte}|{puissance}"] = {
                    "couts": {
                        cle: {
                            "total": str(c.total),
                            "energie": str(c.energie),
                            "abonnement": str(c.abonnement),
                            "kwh": {poste: str(q) for poste, q in sorted(c.kwh.items())},
                            **({"jours_estimes": len(c.jours_estimes)} if c.jours_estimes else {}),
                        }
                        for cle, c in sorted(comp.couts.items())
                    },
                    "indisponibles": dict(sorted(comp.indisponibles.items())),
                }
    return resultats


if __name__ == "__main__":
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(calculer(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"écrit : {FICHIER}")
