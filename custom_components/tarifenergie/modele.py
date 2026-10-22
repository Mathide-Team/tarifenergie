"""Grilles des tarifs réglementés de vente d'électricité (TRVE), d'après l'open data de la CRE.

Fichiers ``tarifs/Option_*.csv`` : copies sans modification des jeux de données
publiés par la Commission de régulation de l'énergie (voir ``docs/sources.md``) :
une ligne par période de validité et par puissance souscrite, prix HT et TTC,
abonnement annuel en €/an, prix du kWh en €/kWh, séparateur « ; », virgule décimale.

Python pur : aucun import Home Assistant (testable seul).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

DOSSIER_TARIFS = Path(__file__).parent / "tarifs"

# Poste horaire → colonne TTC du fichier CRE, par option.
COLONNES: dict[str, dict[str, str]] = {
    "base": {"base": "PART_VARIABLE_TTC"},
    "hphc": {"hp": "PART_VARIABLE_HP_TTC", "hc": "PART_VARIABLE_HC_TTC"},
}
FICHIERS = {"base": "Option_Base.csv", "hphc": "Option_HPHC.csv"}


class TarifIntrouvable(LookupError):
    """Aucune grille en vigueur pour cette option, cette puissance et ce jour."""


@dataclass(frozen=True, slots=True)
class Grille:
    """Une ligne de la CRE : prix TTC valables du ``debut`` au ``fin`` inclus (``None`` : en vigueur)."""

    option: str
    puissance: int
    debut: date
    fin: date | None
    abonnement_an: Decimal
    prix: dict[str, Decimal]

    def couvre(self, jour: date) -> bool:
        _LOGGER.debug("Grille.couvre: entrée")
        _LOGGER.debug("Grille.couvre: sortie")
        return self.debut <= jour and (self.fin is None or jour <= self.fin)


def _decimal(texte: str) -> Decimal | None:
    _LOGGER.debug("_decimal: entrée")
    texte = texte.strip().replace(",", ".")
    if not texte:
        _LOGGER.debug("_decimal: -> None")
        return None
    try:
        _LOGGER.debug("_decimal: sortie")
        return Decimal(texte)
    except InvalidOperation as err:
        _LOGGER.debug("_decimal: %s : %s", type(err).__name__, err)
        _LOGGER.debug("_decimal: lève une exception")
        raise ValueError(f"nombre invalide dans la grille CRE : {texte!r}") from err


def _date(texte: str) -> date | None:
    _LOGGER.debug("_date: entrée")
    texte = texte.strip()
    _LOGGER.debug("_date: sortie")
    return datetime.strptime(texte, "%d/%m/%Y").date() if texte else None


def lire_grilles(option: str, chemin: Path | None = None) -> list[Grille]:
    """Lit un fichier CRE. Les lignes sans prix (puissance non proposée) sont ignorées."""
    _LOGGER.debug("lire_grilles: entrée")
    colonnes = COLONNES[option]
    chemin = chemin or DOSSIER_TARIFS / FICHIERS[option]
    grilles: list[Grille] = []
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        for ligne in csv.DictReader(fichier, delimiter=";"):
            abonnement = _decimal(ligne["PART_FIXE_TTC"])
            prix = {poste: _decimal(ligne[col]) for poste, col in colonnes.items()}
            if abonnement is None or any(p is None for p in prix.values()):
                continue
            debut = _date(ligne["DATE_DEBUT"])
            if debut is None:
                _LOGGER.debug("lire_grilles: lève une exception")
                raise ValueError(f"ligne sans DATE_DEBUT dans {chemin.name}")
            grilles.append(
                Grille(
                    option=option,
                    puissance=int(ligne["P_SOUSCRITE"]),
                    debut=debut,
                    fin=_date(ligne["DATE_FIN"]),
                    abonnement_an=abonnement,
                    prix=prix,  # type: ignore[arg-type]  # aucun None (vérifié ci-dessus)
                )
            )
    _LOGGER.debug("lire_grilles: %s grille(s)", len(grilles))
    return grilles


class Grilles:
    """Index des grilles d'une option, par puissance, pour retrouver le tarif d'un jour."""

    def __init__(self, grilles: list[Grille]) -> None:
        _LOGGER.debug("Grilles.__init__: entrée")
        self._par_puissance: dict[int, list[Grille]] = {}
        for grille in sorted(grilles, key=lambda g: g.debut):
            self._par_puissance.setdefault(grille.puissance, []).append(grille)
        _LOGGER.debug("Grilles.__init__: fin")

    @classmethod
    def charger(cls, option: str) -> Grilles:
        _LOGGER.debug("Grilles.charger: entrée")
        _LOGGER.debug("Grilles.charger: sortie")
        return cls(lire_grilles(option))

    def puissances(self) -> list[int]:
        _LOGGER.debug("Grilles.puissances: entrée")
        _LOGGER.debug("Grilles.puissances: sortie")
        return sorted(self._par_puissance)

    def en_vigueur(self, puissance: int, jour: date) -> Grille:
        _LOGGER.debug("Grilles.en_vigueur: entrée")
        for grille in reversed(self._par_puissance.get(puissance, [])):
            if grille.couvre(jour):
                _LOGGER.debug("Grilles.en_vigueur: %s", grille)
                return grille
        _LOGGER.debug("Grilles.en_vigueur: lève une exception")
        raise TarifIntrouvable(f"pas de tarif {puissance} kVA au {jour.isoformat()}")

    def derniere(self, puissance: int) -> Grille | None:
        _LOGGER.debug("Grilles.derniere: entrée")
        liste = self._par_puissance.get(puissance)
        _LOGGER.debug("Grilles.derniere: sortie")
        return liste[-1] if liste else None
