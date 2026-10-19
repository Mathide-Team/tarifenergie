"""Calendriers tarifaires : à quel poste revient chaque kWh d'une heure (#339).

Chaque offre-option a **son** calendrier, déduit des postes de sa grille : le moteur
(``calcul.py``) ne connaît que l'interface :class:`Calendrier` et ne mélange jamais deux
offres-options. Les structures à venir s'ajoutent ici, une classe par structure, sans
toucher au moteur :

- Tempo : jours bleus / blancs / rouges x HP / HC (#340) ;
- heures super creuses : HP / HC / HSC, plages saisonnières fixées par le fournisseur (#341) ;
- week-end et heures atypiques : poste par jour de semaine (#342).

Les plages d'heures creuses du TRV et des offres HP/HC sont celles **du compteur**
(fixées par le gestionnaire de réseau), saisies par l'utilisateur. Les plages propres à
une offre-option (HSC, week-end) viendront de son fichier YAML, jamais de cette saisie.

Python pur : aucun import Home Assistant (testable seul).
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Protocol

MINUTES_JOUR = 24 * 60
_PLAGE = re.compile(r"^\s*(\d{1,2})[:h](\d{2})\s*-\s*(\d{1,2})[:h](\d{2})\s*$")


class PlagesInvalides(ValueError):
    """Texte d'heures creuses illisible."""


class PostesNonPrisEnCharge(ValueError):
    """Aucun calendrier ne sait répartir ces postes (structure pas encore implémentée)."""


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


class Calendrier(Protocol):
    """Répartit les kWh d'une heure entre les postes d'une offre-option."""

    postes: ClassVar[frozenset[str]]

    def repartir(self, debut: datetime, kwh: Decimal) -> dict[str, Decimal]:
        """``debut`` : début de l'heure, en heure locale ; la somme des parts vaut ``kwh``."""
        ...


@dataclass(frozen=True, slots=True)
class CalendrierBase:
    """Un seul prix toute l'année."""

    postes: ClassVar[frozenset[str]] = frozenset({"base"})

    def repartir(self, debut: datetime, kwh: Decimal) -> dict[str, Decimal]:
        return {"base": kwh}


@dataclass(frozen=True, slots=True)
class CalendrierHPHC:
    """Heures pleines / heures creuses du compteur ; une heure à cheval sur une limite
    (ex. 23:30) est répartie au prorata des minutes, faute de mesure plus fine."""

    plages: PlagesHC
    postes: ClassVar[frozenset[str]] = frozenset({"hp", "hc"})

    def repartir(self, debut: datetime, kwh: Decimal) -> dict[str, Decimal]:
        hc = kwh * self.plages.fraction_hc(debut.hour)
        return {"hc": hc, "hp": kwh - hc}


def calendrier_pour(postes: Iterable[str], plages: PlagesHC | None) -> Calendrier:
    """Calendrier d'une offre-option d'après les postes de sa grille.

    Lève :class:`PostesNonPrisEnCharge` pour une structure pas encore implémentée
    (Tempo, heures super creuses, week-end : #340 à #342), et ``ValueError`` si une
    option heures creuses n'a pas de plages.
    """
    postes = frozenset(postes)
    if postes == CalendrierBase.postes:
        return CalendrierBase()
    if postes == CalendrierHPHC.postes:
        if plages is None:
            raise ValueError("l'option heures creuses demande des plages")
        return CalendrierHPHC(plages)
    raise PostesNonPrisEnCharge(f"postes non pris en charge : {', '.join(sorted(postes))}")
