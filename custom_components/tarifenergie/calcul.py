"""Moteur de comparaison : coût de chaque offre-option sur une consommation horaire réelle.

Principe (issues #2 et #343) :
    - une **offre-option** (TRV Base, TRV HP/HC, ou une option d'une offre de marché)
      est calculée seule, avec ses grilles et son calendrier : aucune offre-option
      n'est regroupée avec une autre, même si elles viennent du même fournisseur ;
    - chaque heure consommée est valorisée au prix TTC **en vigueur ce jour-là**
      (date locale), selon le poste que lui attribue le calendrier de l'offre-option
      (``calendrier.py``) ;
    - l'abonnement annuel TTC est compté au jour : 1/365 (ou 1/366) par jour
      couvert, avec la grille du jour ;
    - une offre-option sans grille, non éligible ou de structure non prise en charge
      est mise de côté avec la raison.

Python pur : aucun import Home Assistant (testable seul).
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .calendrier import (
    Calendrier,
    CalendrierHPHC,
    CalendrierTempo,
    DonneesManquantes,
    PlagesDatees,
    PlagesHC,
    PostesNonPrisEnCharge,
    calendrier_pour,
)
from .calendrier import PlagesInvalides as PlagesInvalides  # réexport (config_flow, tests)
from .modele import Grilles, TarifIntrouvable
from .tempo import CouleurInconnue, CouleursTempo, jour_tempo

CENTIME = Decimal("0.01")


@dataclass(slots=True)
class Cout:
    """Coût d'une option sur la période couverte par la consommation."""

    option: str
    energie: Decimal = Decimal(0)
    abonnement: Decimal = Decimal(0)
    kwh: dict[str, Decimal] = field(default_factory=dict)
    # Débuts des grilles CRE utilisées (traçabilité : « tarif du 01/08/2026 »).
    grilles: set[date] = field(default_factory=set)
    # Tempo : jours dont la couleur a été estimée (manquante dans l'historique réel).
    jours_estimes: set[date] = field(default_factory=set)
    # HP/HC : périodes de plages du compteur réellement appliquées (#369).
    plages_hc: list[dict[str, str | None]] = field(default_factory=list)

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
            **({"jours_couleur_estimee": len(self.jours_estimes)} if self.jours_estimes else {}),
            **({"plages_hc": self.plages_hc} if self.plages_hc else {}),
        }


def _jours_annee(jour: date) -> int:
    return 366 if calendar.isleap(jour.year) else 365


def cout_option(
    option: str,
    grilles: Grilles,
    puissance: int,
    conso: Iterable[tuple[datetime, float]],
    plages: PlagesHC | PlagesDatees | None = None,
    jours: Iterable[date] | None = None,
    couleurs: CouleursTempo | None = None,
) -> Cout:
    """Coût TTC de l'offre-option ``option`` pour une consommation horaire.

    ``conso`` : couples (début d'heure en heure **locale**, kWh consommés dans l'heure).
    ``plages`` : heures creuses du compteur, pour un calendrier HP/HC.
    ``jours`` : jours d'abonnement à compter ; par défaut, ceux présents dans ``conso``.
    ``couleurs`` : couleurs des jours passés, pour un calendrier Tempo (réelles ou estimées).
    Lève :class:`TarifIntrouvable` si un jour n'a pas de grille (puissance non proposée…),
    :class:`PostesNonPrisEnCharge` pour une structure pas encore implémentée et
    :class:`CouleurInconnue` pour un jour Tempo sans couleur.
    """
    if option == "hphc" and plages is None:
        raise ValueError("l'option heures creuses demande des plages")
    cout = Cout(option)
    vus: set[date] = set()
    # Calendrier déduit des postes de la grille du jour (une offre-option garde les
    # mêmes postes d'une grille à l'autre ; le cache évite de le reconstruire).
    calendriers: dict[frozenset[str], Calendrier] = {}
    periodes_hc: set[int] = set()
    for debut, kwh in conso:
        jour = debut.date()
        vus.add(jour)
        if not kwh:
            continue
        grille = grilles.en_vigueur(puissance, jour)
        cout.grilles.add(grille.debut)
        postes = frozenset(grille.prix)
        if postes not in calendriers:
            calendriers[postes] = calendrier_pour(postes, plages, couleurs)
        calendrier = calendriers[postes]
        repartition = calendrier.repartir(debut, Decimal(str(kwh)))
        if isinstance(calendrier, CalendrierHPHC):
            periodes_hc.add(calendrier.plages.rang(jour))
        elif isinstance(calendrier, CalendrierTempo):
            jour_couleur = jour_tempo(debut)
            if jour_couleur in calendrier.couleurs.estimes:
                cout.jours_estimes.add(jour_couleur)
        for poste, q in repartition.items():
            cout.kwh[poste] = cout.kwh.get(poste, Decimal(0)) + q
            cout.energie += q * grille.prix[poste]
    if periodes_hc:
        calendrier_hc = next(c for c in calendriers.values() if isinstance(c, CalendrierHPHC))
        cout.plages_hc = calendrier_hc.plages.resume(periodes_hc)
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
    plages: PlagesHC | PlagesDatees,
    option_actuelle: str,
    exclues: dict[str, str] | None = None,
    couleurs: CouleursTempo | None = None,
) -> Comparaison:
    """Calcule chaque offre-option séparément, sur la même consommation.

    ``grilles`` : une entrée par offre-option (clé de comparaison → ses grilles).
    ``exclues`` : offres-options écartées d'avance (non éligibles…), avec la raison.
    ``couleurs`` : couleurs Tempo des jours passés (réelles, ou estimées selon les règles).
    Une offre-option sans tarif pour cette puissance, de structure non prise en charge
    ou sans donnée nécessaire (couleurs Tempo…) est mise de côté avec la raison ; les
    autres restent comparées.
    """
    exclues = exclues or {}
    jours = {debut.date() for debut, _ in conso}
    couts: dict[str, Cout] = {}
    indisponibles: dict[str, str] = {}
    for option, grilles_option in grilles.items():
        if option in exclues:
            indisponibles[option] = exclues[option]
            continue
        try:
            couts[option] = cout_option(option, grilles_option, puissance, conso, plages, jours, couleurs)
        except (TarifIntrouvable, PostesNonPrisEnCharge, DonneesManquantes, CouleurInconnue) as err:
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
