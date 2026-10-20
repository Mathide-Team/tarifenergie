"""Calendriers tarifaires : à quel poste revient chaque kWh d'une heure (#339).

Chaque offre-option a **son** calendrier, déduit des postes de sa grille : le moteur
(``calcul.py``) ne connaît que l'interface :class:`Calendrier` et ne mélange jamais deux
offres-options. Les structures à venir s'ajoutent ici, une classe par structure, sans
toucher au moteur :

- Tempo : jours bleus / blancs / rouges x HP / HC (#340), :class:`CalendrierTempo` ;
- heures super creuses : HP / HC / HSC, plages saisonnières fixées par le fournisseur (#341) ;
- week-end et heures atypiques : poste par jour de semaine (#342).

Les plages d'heures creuses du TRV et des offres HP/HC sont celles **du compteur**
(fixées par le gestionnaire de réseau), saisies par l'utilisateur ou détectées depuis la
téléinformation (#370). Elles peuvent changer en cours d'année : :class:`PlagesDatees`
(#369). Les plages propres à une offre-option (Tempo, HSC, Zen Flex, week-end) viennent de
l'offre-option, jamais de cette saisie.

Python pur : aucun import Home Assistant (testable seul).
"""

from __future__ import annotations

import bisect
import itertools
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar, Protocol

from .tempo import COULEURS, HEURE_DEBUT_JOUR_TEMPO, CouleursTempo, jour_tempo

MINUTES_JOUR = 24 * 60
_PLAGE = re.compile(r"^\s*(\d{1,2})[:h](\d{2})\s*-\s*(\d{1,2})[:h](\d{2})\s*$")
_PERIODE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s*:\s*(.*)$", re.DOTALL)
SEPARATEUR_PERIODES = "|"


class PlagesInvalides(ValueError):
    """Texte d'heures creuses illisible."""


class DonneesManquantes(ValueError):
    """Le calendrier d'une offre-option demande une donnée absente (plages HC, couleurs Tempo)."""


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


# Saisons des plages HC du compteur (réforme Enedis, #368) : été du 1er avril au 31 octobre,
# hiver du 1er novembre au 31 mars.
MOIS_DEBUT_ETE = 4
MOIS_DEBUT_HIVER = 11
SEPARATEUR_SAISONS = "/"
_SAISON = re.compile(r"^\s*(été|ete|summer|hiver|winter)\s*:?\s*(.*)$", re.IGNORECASE | re.DOTALL)
_HIVER = ("hiver", "winter")


def est_hiver(jour: date) -> bool:
    return jour.month >= MOIS_DEBUT_HIVER or jour.month < MOIS_DEBUT_ETE


@dataclass(frozen=True, slots=True)
class PlagesSaisonnieres:
    """Plages HC du compteur différentes en été et en hiver, reconduites chaque année (#368)."""

    ete: PlagesHC
    hiver: PlagesHC

    @classmethod
    def lire(cls, texte: str) -> PlagesSaisonnieres:
        """``"été 02:00-07:00, 13:00-16:00 / hiver 23:00-07:00"`` (ordre libre)."""
        saisons: dict[str, PlagesHC] = {}
        for morceau in texte.split(SEPARATEUR_SAISONS):
            trouve = _SAISON.match(morceau)
            if not trouve:
                raise PlagesInvalides(f"saison attendue (été ou hiver) : {morceau.strip()!r}")
            saison = "hiver" if trouve.group(1).lower() in _HIVER else "ete"
            if saison in saisons:
                raise PlagesInvalides(f"saison en double : {trouve.group(1)}")
            saisons[saison] = PlagesHC.lire(trouve.group(2))
        if len(saisons) != 2:
            raise PlagesInvalides("plages saisonnières : il faut l'été et l'hiver")
        return cls(saisons["ete"], saisons["hiver"])

    def du_jour(self, jour: date) -> PlagesHC:
        return self.hiver if est_hiver(jour) else self.ete

    def texte(self) -> str:
        return f"été {self.ete.texte()} {SEPARATEUR_SAISONS} hiver {self.hiver.texte()}"


def _lire_plages(texte: str) -> PlagesHC | PlagesSaisonnieres:
    if SEPARATEUR_SAISONS in texte or _SAISON.match(texte):
        return PlagesSaisonnieres.lire(texte)
    return PlagesHC.lire(texte)


@dataclass(frozen=True, slots=True)
class PlagesDatees:
    """Plages HC du compteur qui changent en cours d'année (#369).

    ``periodes`` : ``(depuis, plages)`` par date croissante ; la première période n'a pas
    de date (``None`` : plages d'avant le premier changement). Les plages d'une période
    valent du jour ``depuis`` à 0h jusqu'à la veille du changement suivant. Une période
    peut avoir des plages d'été et d'hiver (:class:`PlagesSaisonnieres`, #368).
    """

    periodes: tuple[tuple[date | None, PlagesHC | PlagesSaisonnieres], ...]

    @classmethod
    def uniques(cls, plages: PlagesHC | PlagesSaisonnieres) -> PlagesDatees:
        return cls(((None, plages),))

    @classmethod
    def lire(cls, texte: str) -> PlagesDatees:
        """``"22:00-06:00"``, ``"22:00-06:00 | 2026-03-15: 02:00-07:00, 13:00-16:00"``,
        ``"été 02:00-07:00, 13:00-16:00 / hiver 23:00-07:00"`` ; périodes et saisons combinables."""
        periodes: list[tuple[date | None, PlagesHC | PlagesSaisonnieres]] = []
        for rang, morceau in enumerate(texte.split(SEPARATEUR_PERIODES)):
            trouve = _PERIODE.match(morceau)
            if rang == 0:
                if trouve:
                    raise PlagesInvalides(
                        "la première période n'a pas de date : plages d'avant le premier changement"
                    )
                periodes.append((None, _lire_plages(morceau)))
                continue
            if not trouve:
                raise PlagesInvalides(
                    f"changement sans date : {morceau.strip()!r} (attendu AAAA-MM-JJ: plages)"
                )
            try:
                depuis = date.fromisoformat(trouve.group(1))
            except ValueError:
                raise PlagesInvalides(f"date illisible : {trouve.group(1)!r}") from None
            precedente = periodes[-1][0]
            if precedente is not None and depuis <= precedente:
                raise PlagesInvalides(
                    f"dates non croissantes : {depuis.isoformat()} après {precedente.isoformat()}"
                )
            periodes.append((depuis, _lire_plages(trouve.group(2))))
        return cls(tuple(periodes))

    @property
    def _dates(self) -> list[date]:
        return [depuis for depuis, _ in self.periodes[1:] if depuis is not None]

    def rang(self, jour: date) -> int:
        """Rang de la période en vigueur le ``jour``."""
        return bisect.bisect_right(self._dates, jour)

    def du_jour(self, jour: date) -> PlagesHC:
        plages = self.periodes[self.rang(jour)][1]
        return plages.du_jour(jour) if isinstance(plages, PlagesSaisonnieres) else plages

    def texte(self) -> str:
        return f" {SEPARATEUR_PERIODES} ".join(
            plages.texte() if depuis is None else f"{depuis.isoformat()}: {plages.texte()}"
            for depuis, plages in self.periodes
        )

    def resume(self, rangs: Iterable[int] | None = None) -> list[dict[str, str | None]]:
        """Périodes (toutes, ou les ``rangs`` utilisés) pour un attribut de capteur."""
        choisis = sorted(set(range(len(self.periodes)) if rangs is None else rangs))
        return [
            {
                "depuis": None if self.periodes[r][0] is None else self.periodes[r][0].isoformat(),
                "plages": self.periodes[r][1].texte(),
            }
            for r in choisis
        ]


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
    """Heures pleines / heures creuses du compteur, avec les plages **du jour** (#369) ;
    une heure à cheval sur une limite (ex. 23:30) est répartie au prorata des minutes,
    faute de mesure plus fine."""

    plages: PlagesDatees
    postes: ClassVar[frozenset[str]] = frozenset({"hp", "hc"})

    def repartir(self, debut: datetime, kwh: Decimal) -> dict[str, Decimal]:
        hc = kwh * self.plages.du_jour(debut.date()).fraction_hc(debut.hour)
        return {"hc": hc, "hp": kwh - hc}


# Tempo : heures creuses fixes de 22h à 6h, sur tout le territoire (pas les plages du compteur).
TEMPO_DEBUT_HC = 22
POSTES_TEMPO: frozenset[str] = frozenset(f"{p}_{c}" for p in ("hp", "hc") for c in COULEURS)


@dataclass(frozen=True, slots=True)
class CalendrierTempo:
    """Tempo (#340) : couleur du jour Tempo (de 6h à 6h) x heures pleines / creuses (22h-6h).

    Les heures de 0h à 6h prennent la couleur de la veille : après un jour rouge, elles
    sont rouges, même un samedi ou un jour férié. Les couleurs sont celles des jours passés
    (réelles, ou estimées selon les règles : ``tempo.py``), jamais une prévision.
    """

    couleurs: CouleursTempo
    postes: ClassVar[frozenset[str]] = POSTES_TEMPO

    def repartir(self, debut: datetime, kwh: Decimal) -> dict[str, Decimal]:
        heure = debut.hour
        poste = "hc" if heure >= TEMPO_DEBUT_HC or heure < HEURE_DEBUT_JOUR_TEMPO else "hp"
        return {f"{poste}_{self.couleurs.couleur(jour_tempo(debut))}": kwh}


def calendrier_pour(
    postes: Iterable[str],
    plages: PlagesHC | PlagesDatees | None,
    couleurs: CouleursTempo | None = None,
) -> Calendrier:
    """Calendrier d'une offre-option d'après les postes de sa grille.

    Lève :class:`PostesNonPrisEnCharge` pour une structure pas encore implémentée
    (heures super creuses, week-end : #341, #342), et ``ValueError`` si une option
    heures creuses n'a pas de plages ou une option Tempo pas de couleurs
    (:class:`DonneesManquantes`).
    """
    postes = frozenset(postes)
    if postes == CalendrierBase.postes:
        return CalendrierBase()
    if postes == CalendrierHPHC.postes:
        if plages is None:
            raise DonneesManquantes("l'option heures creuses demande des plages")
        return CalendrierHPHC(plages if isinstance(plages, PlagesDatees) else PlagesDatees.uniques(plages))
    if postes == POSTES_TEMPO:
        if couleurs is None:
            raise DonneesManquantes("l'option Tempo demande les couleurs des jours")
        return CalendrierTempo(couleurs)
    raise PostesNonPrisEnCharge(f"postes non pris en charge : {', '.join(sorted(postes))}")
