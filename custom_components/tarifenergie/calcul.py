"""Moteur de comparaison : coût d'une option tarifaire sur une consommation horaire réelle.

Principe (issue #2) :
    - chaque heure consommée est valorisée au prix TTC **en vigueur ce jour-là**
      (date locale), selon son poste (base, ou heures pleines / creuses) ;
    - l'abonnement annuel TTC est compté au jour : 1/365 (ou 1/366) par jour
      couvert, avec la grille du jour ;
    - une heure à cheval sur une limite d'heures creuses (ex. 23:30) est
      répartie au prorata des minutes, faute de mesure plus fine.

Python pur : aucun import Home Assistant (testable seul).
"""

from __future__ import annotations

import calendar
import itertools
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .modele import Grilles, TarifIntrouvable

CENTIME = Decimal("0.01")
MINUTES_JOUR = 24 * 60
_PLAGE = re.compile(r"^\s*(\d{1,2})[:h](\d{2})\s*-\s*(\d{1,2})[:h](\d{2})\s*$")


class PlagesInvalides(ValueError):
    """Texte d'heures creuses illisible."""


@dataclass(frozen=True, slots=True)
class PlagesHC:
    """Plages d'heures creuses, en minutes depuis minuit (fin exclue, passage de minuit permis)."""

    plages: tuple[tuple[int, int], ...]

    @classmethod
    def lire(cls, texte: str) -> PlagesHC:
        """``"22:00-06:00"`` ou ``"02:00-07:00, 13:00-16:00"`` (le « h » est accepté : ``22h00``)."""
        plages: list[tuple[int, int]] = []
        for morceau in filter(None, (m.strip() for m in re.split(r"[,;]", texte))):
            trouve = _PLAGE.match(morceau)
            if not trouve:
                raise PlagesInvalides(f"plage illisible : {morceau!r} (attendu HH:MM-HH:MM)")
            h1, m1, h2, m2 = (int(x) for x in trouve.groups())
            if h1 > 23 or h2 > 24 or m1 > 59 or m2 > 59 or (h2 == 24 and m2):
                raise PlagesInvalides(f"heure impossible : {morceau!r}")
            debut, fin = h1 * 60 + m1, h2 * 60 + m2
            if debut == fin % MINUTES_JOUR:
                raise PlagesInvalides(f"plage vide ou de 24 h : {morceau!r}")
            plages.append((debut, fin))
        if not plages:
            raise PlagesInvalides("aucune plage d'heures creuses")
        resultat = cls(tuple(plages))
        intervalles = sorted(resultat._intervalles())
        for (_, fin_a), (debut_b, _) in itertools.pairwise(intervalles):
            if debut_b < fin_a:
                raise PlagesInvalides(f"plages qui se chevauchent : {texte!r}")
        return resultat

    def _intervalles(self) -> Iterable[tuple[int, int]]:
        """Intervalles sans passage de minuit, dans [0, 1440]."""
        for debut, fin in self.plages:
            if fin > debut:
                yield debut, fin
            else:
                yield debut, MINUTES_JOUR
                if fin:
                    yield 0, fin

    def minutes_par_jour(self) -> int:
        return sum(fin - debut for debut, fin in self._intervalles())

    def fraction_hc(self, heure: int) -> Decimal:
        """Part (0 à 1) de l'heure locale ``heure``:00-``heure+1``:00 en heures creuses."""
        debut_h, fin_h = heure * 60, heure * 60 + 60
        minutes = sum(max(0, min(fin, fin_h) - max(debut, debut_h)) for debut, fin in self._intervalles())
        return Decimal(min(minutes, 60)) / 60

    def texte(self) -> str:
        return ", ".join(f"{d // 60:02d}:{d % 60:02d}-{f // 60:02d}:{f % 60:02d}" for d, f in self.plages)


@dataclass(slots=True)
class Cout:
    """Coût d'une option sur la période couverte par la consommation."""

    option: str
    energie: Decimal = Decimal(0)
    abonnement: Decimal = Decimal(0)
    kwh: dict[str, Decimal] = field(default_factory=dict)
    # Débuts des grilles CRE utilisées (traçabilité : « tarif du 01/08/2026 »).
    grilles: set[date] = field(default_factory=set)

    @property
    def total(self) -> Decimal:
        return (self.energie + self.abonnement).quantize(CENTIME, ROUND_HALF_UP)

    def arrondi(self) -> dict[str, object]:
        return {
            "option": self.option,
            "total": self.total,
            "energie": self.energie.quantize(CENTIME, ROUND_HALF_UP),
            "abonnement": self.abonnement.quantize(CENTIME, ROUND_HALF_UP),
            "kwh": {poste: round(float(v), 3) for poste, v in sorted(self.kwh.items())},
            "grilles": sorted(d.isoformat() for d in self.grilles),
        }


def _jours_annee(jour: date) -> int:
    return 366 if calendar.isleap(jour.year) else 365


def cout_option(
    option: str,
    grilles: Grilles,
    puissance: int,
    conso: Iterable[tuple[datetime, float]],
    plages: PlagesHC | None = None,
    jours: Iterable[date] | None = None,
) -> Cout:
    """Coût TTC de ``option`` pour une consommation horaire.

    ``conso`` : couples (début d'heure en heure **locale**, kWh consommés dans l'heure).
    ``jours`` : jours d'abonnement à compter ; par défaut, ceux présents dans ``conso``.
    Lève :class:`TarifIntrouvable` si un jour n'a pas de grille (puissance non proposée…).
    """
    if option == "hphc" and plages is None:
        raise ValueError("l'option heures creuses demande des plages")
    cout = Cout(option)
    vus: set[date] = set()
    for debut, kwh in conso:
        jour = debut.date()
        vus.add(jour)
        if not kwh:
            continue
        grille = grilles.en_vigueur(puissance, jour)
        cout.grilles.add(grille.debut)
        quantite = Decimal(str(kwh))
        # Base ou Heures creuses : selon les postes de la grille (TRV « base »/«hphc »
        # ou offre de marché « <id>:<option> »), pas selon la clé exacte.
        if set(grille.prix) == {"base"}:
            repartition = {"base": quantite}
        else:
            if plages is None:
                raise ValueError("l'option heures creuses demande des plages")
            hc = quantite * plages.fraction_hc(debut.hour)
            repartition = {"hc": hc, "hp": quantite - hc}
        for poste, q in repartition.items():
            cout.kwh[poste] = cout.kwh.get(poste, Decimal(0)) + q
            cout.energie += q * grille.prix[poste]
    for jour in sorted(vus if jours is None else set(jours)):
        grille = grilles.en_vigueur(puissance, jour)
        cout.grilles.add(grille.debut)
        cout.abonnement += grille.abonnement_an / _jours_annee(jour)
    return cout


@dataclass(frozen=True, slots=True)
class Comparaison:
    """Classement des options calculables, du moins cher au plus cher."""

    couts: dict[str, Cout]
    indisponibles: dict[str, str]
    option_actuelle: str
    jours: int

    @property
    def classement(self) -> list[Cout]:
        return sorted(self.couts.values(), key=lambda c: (c.total, c.option))

    @property
    def moins_chere(self) -> Cout | None:
        return self.classement[0] if self.couts else None

    @property
    def economie(self) -> Decimal | None:
        """Économie de l'option la moins chère par rapport à l'option actuelle (0 si déjà la meilleure)."""
        actuelle = self.couts.get(self.option_actuelle)
        meilleure = self.moins_chere
        if actuelle is None or meilleure is None:
            return None
        return actuelle.total - meilleure.total


def comparer(
    grilles: dict[str, Grilles],
    puissance: int,
    conso: list[tuple[datetime, float]],
    plages: PlagesHC,
    option_actuelle: str,
) -> Comparaison:
    """Calcule toutes les options ; une option sans tarif pour cette puissance est mise de côté."""
    jours = {debut.date() for debut, _ in conso}
    couts: dict[str, Cout] = {}
    indisponibles: dict[str, str] = {}
    for option, grilles_option in grilles.items():
        try:
            couts[option] = cout_option(option, grilles_option, puissance, conso, plages, jours)
        except TarifIntrouvable as err:
            indisponibles[option] = str(err)
    return Comparaison(couts, indisponibles, option_actuelle, len(jours))


def heures_locales(debut: datetime, fin: datetime) -> list[datetime]:
    """Débuts d'heure de ``debut`` (inclus) à ``fin`` (exclu) — aide pour les tests."""
    heures = []
    courant = debut
    while courant < fin:
        heures.append(courant)
        courant += timedelta(hours=1)
    return heures
