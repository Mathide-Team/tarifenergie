"""Grilles des tarifs réglementés de vente d'électricité (TRVE), d'après l'open data de la CRE.

Fichiers ``tarifs/Option_*.csv`` : copies sans modification des jeux de données
publiés par la Commission de régulation de l'énergie (voir ``docs/sources.md``) :
une ligne par période de validité et par puissance souscrite, prix HT et TTC,
abonnement annuel en €/an, prix du kWh en €/kWh, séparateur « ; », virgule décimale.

Python pur : aucun import Home Assistant (testable seul).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

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
        return self.debut <= jour and (self.fin is None or jour <= self.fin)


def _decimal(texte: str) -> Decimal | None:
    texte = texte.strip().replace(",", ".")
    if not texte:
        return None
    try:
        return Decimal(texte)
    except InvalidOperation as err:
        raise ValueError(f"nombre invalide dans la grille CRE : {texte!r}") from err


def _date(texte: str) -> date | None:
    texte = texte.strip()
    return datetime.strptime(texte, "%d/%m/%Y").date() if texte else None


def lire_grilles(option: str, chemin: Path | None = None) -> list[Grille]:
    """Lit un fichier CRE. Les lignes sans prix (puissance non proposée) sont ignorées."""
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
    return grilles


class Grilles:
    """Index des grilles d'une option, par puissance, pour retrouver le tarif d'un jour."""

    def __init__(self, grilles: list[Grille]) -> None:
        self._par_puissance: dict[int, list[Grille]] = {}
        for grille in sorted(grilles, key=lambda g: g.debut):
            self._par_puissance.setdefault(grille.puissance, []).append(grille)

    @classmethod
    def charger(cls, option: str) -> Grilles:
        return cls(lire_grilles(option))

    def puissances(self) -> list[int]:
        return sorted(self._par_puissance)

    def en_vigueur(self, puissance: int, jour: date) -> Grille:
        for grille in reversed(self._par_puissance.get(puissance, [])):
            if grille.couvre(jour):
                return grille
        raise TarifIntrouvable(f"pas de tarif {puissance} kVA au {jour.isoformat()}")

    def derniere(self, puissance: int) -> Grille | None:
        liste = self._par_puissance.get(puissance)
        return liste[-1] if liste else None
