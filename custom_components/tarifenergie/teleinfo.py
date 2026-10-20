"""Détection des plages HP/HC du compteur depuis la téléinformation (#370).

Avec un module de téléinformation branché sur le Linky, Home Assistant reçoit les index
**heures creuses** et **heures pleines** du compteur (capteurs d'énergie cumulée). Leurs
statistiques horaires sont conservées à long terme : sur la fenêtre simulée, une heure où
seul l'index HC avance est une heure creuse, une heure où les deux avancent est à cheval
sur une limite (demi-heure).

L'état texte « période tarifaire en cours » (PTEC / LTARF) n'est pas utilisé : le recorder
ne le garde que quelques jours.

Algorithme, jour par jour, au pas de la demi-heure :

1. part HC de chaque heure = kWh HC / (kWh HC + kWh HP) : au moins 3/4 → heure creuse,
   au plus 1/4 → heure pleine, entre les deux → heure à cheval (la demi-heure creuse est
   du côté de l'heure voisine creuse) ;
2. heure sans consommation, ou à cheval sans voisine pour trancher : reprise du jour
   précédent ; un jour encore incomplet est ignoré ;
3. regroupement en plages datées : un nouveau jeu de plages ne compte que s'il dure au
   moins :data:`JOURS_MINIMUM` jours consécutifs (un jour atypique ne crée pas de
   changement) ; le changement est daté de son premier jour ;
4. saisons (#368) : au moins deux changements successifs qui alternent entre deux jeux
   de plages, chacun à moins de :data:`TOLERANCE_BASCULE` jours d'un 1er avril (été) ou
   d'un 1er novembre (hiver), deviennent des plages saisonnières, reconduites chaque année.

Les index doivent être ceux du **gestionnaire de réseau** (plages du compteur), pas ceux
d'un calendrier fournisseur (Tempo, Zen Flex…).

Python pur : aucun import Home Assistant (testable seul).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

from .calendrier import (
    MINUTES_JOUR,
    MOIS_DEBUT_ETE,
    MOIS_DEBUT_HIVER,
    PlagesDatees,
    PlagesHC,
    PlagesSaisonnieres,
)

PAS_MINUTES = 30
CRENEAUX = MINUTES_JOUR // PAS_MINUTES
JOURS_MINIMUM = 3
SEUIL_KWH = 0.005  # en dessous, l'heure est muette (pas de consommation mesurable)
PART_CREUSE = 0.75
PART_PLEINE = 0.25
TOLERANCE_BASCULE = 3  # jours d'écart admis autour du 1er avril et du 1er novembre

Signature = tuple[bool, ...]


def _heures(index: Iterable[tuple[datetime, float]]) -> dict[date, dict[int, float]]:
    """kWh par jour et par heure locale (heure doublée au changement d'heure : cumulée)."""
    cumul: dict[date, dict[int, float]] = {}
    for debut, kwh in index:
        heures = cumul.setdefault(debut.date(), {})
        heures[debut.hour] = heures.get(debut.hour, 0.0) + max(kwh, 0.0)
    return cumul


def _etat_heures(hc: dict[int, float], hp: dict[int, float]) -> list[str | None]:
    """Par heure : ``"hc"``, ``"hp"``, ``"mixte"`` ou ``None`` (muette)."""
    etats: list[str | None] = []
    for heure in range(24):
        creuses, pleines = hc.get(heure, 0.0), hp.get(heure, 0.0)
        total = creuses + pleines
        if total < SEUIL_KWH:
            etats.append(None)
        elif creuses / total >= PART_CREUSE:
            etats.append("hc")
        elif creuses / total <= PART_PLEINE:
            etats.append("hp")
        else:
            etats.append("mixte")
    return etats


def _creneaux(etats: list[str | None], veille: Signature | None) -> Signature | None:
    """48 demi-heures (``True`` = creuse) ; ``None`` si le jour reste incomplet."""
    creneaux: list[bool | None] = [None] * CRENEAUX
    for heure, etat in enumerate(etats):
        if etat in ("hc", "hp"):
            creneaux[2 * heure] = creneaux[2 * heure + 1] = etat == "hc"
    for heure, etat in enumerate(etats):
        if etat != "mixte":
            continue
        avant, apres = etats[heure - 1], etats[(heure + 1) % 24]
        if avant == "hc" or apres == "hp":
            creneaux[2 * heure], creneaux[2 * heure + 1] = True, False
        elif avant == "hp" or apres == "hc":
            creneaux[2 * heure], creneaux[2 * heure + 1] = False, True
    if veille is not None:
        creneaux = [veille[i] if c is None else c for i, c in enumerate(creneaux)]
    if any(c is None for c in creneaux):
        return None
    return tuple(bool(c) for c in creneaux)


def _plages(signature: Signature) -> PlagesHC | None:
    """Plages HC d'une signature (passage de minuit regroupé) ; ``None`` si aucune ou toute la journée."""
    if all(signature) or not any(signature):
        return None
    # Départ sur une demi-heure pleine : une plage qui passe minuit reste d'un seul tenant.
    depart = signature.index(False)
    plages: list[tuple[int, int]] = []
    debut: int | None = None
    for pas in range(1, CRENEAUX + 1):
        i = (depart + pas) % CRENEAUX
        if signature[i] and debut is None:
            debut = i
        elif not signature[i] and debut is not None:
            plages.append((debut * PAS_MINUTES, i * PAS_MINUTES))  # 0 : jusqu'à minuit
            debut = None
    return PlagesHC(tuple(sorted(plages)))


def signatures_par_jour(
    index_hc: Iterable[tuple[datetime, float]], index_hp: Iterable[tuple[datetime, float]]
) -> list[tuple[date, Signature]]:
    """Demi-heures creuses de chaque jour mesuré (jours incomplets omis)."""
    hc, hp = _heures(index_hc), _heures(index_hp)
    resultat: list[tuple[date, Signature]] = []
    veille: Signature | None = None
    for jour in sorted(hc.keys() | hp.keys()):
        etats = _etat_heures(hc.get(jour, {}), hp.get(jour, {}))
        signature = _creneaux(etats, veille)
        if signature is not None:
            resultat.append((jour, signature))
            veille = signature
    return resultat


def detecter_plages(
    index_hc: Iterable[tuple[datetime, float]], index_hp: Iterable[tuple[datetime, float]]
) -> PlagesDatees | None:
    """Plages HC datées vues par le compteur ; ``None`` si rien d'exploitable (pas d'HP/HC)."""
    jours = signatures_par_jour(index_hc, index_hp)
    periodes: list[tuple[date | None, Signature]] = []
    i = 0
    while i < len(jours):
        jour, signature = jours[i]
        if periodes and signature == periodes[-1][1]:
            i += 1
            continue
        suite = 1
        while i + suite < len(jours) and jours[i + suite][1] == signature:
            suite += 1
        if suite >= JOURS_MINIMUM or (not periodes and i + suite == len(jours)):
            periodes.append((None if not periodes else jour, signature))
        i += suite
    resultat: list[tuple[date | None, PlagesHC | PlagesSaisonnieres]] = []
    for depuis, signature in periodes:
        plages = _plages(signature)
        if plages is None:
            continue
        if resultat and resultat[-1][1] == plages:
            continue
        resultat.append((None if not resultat else depuis, plages))
    return PlagesDatees(tuple(_saisonnaliser(resultat))) if resultat else None


def _bascule(jour: date) -> str | None:
    """``"ete"`` / ``"hiver"`` si le jour est à une bascule de saison (à la tolérance près)."""
    for mois, saison in ((MOIS_DEBUT_ETE, "ete"), (MOIS_DEBUT_HIVER, "hiver")):
        if abs((jour - date(jour.year, mois, 1)).days) <= TOLERANCE_BASCULE:
            return saison
    return None


def _saisonnaliser(
    periodes: list[tuple[date | None, PlagesHC | PlagesSaisonnieres]],
) -> list[tuple[date | None, PlagesHC | PlagesSaisonnieres]]:
    """Remplace les alternances été / hiver (au moins deux bascules) par des plages saisonnières."""
    sortie: list[tuple[date | None, PlagesHC | PlagesSaisonnieres]] = []
    i = 0
    while i < len(periodes):
        saisons: dict[str, PlagesHC | PlagesSaisonnieres] = {}
        j = i
        while j + 1 < len(periodes):
            depuis, apres = periodes[j + 1]
            saison = _bascule(depuis) if depuis is not None else None
            if saison is None:
                break
            autre = "hiver" if saison == "ete" else "ete"
            avant = periodes[j][1]
            if saisons.get(saison, apres) != apres or saisons.get(autre, avant) != avant:
                break
            saisons[saison], saisons[autre] = apres, avant
            j += 1
        ete, hiver = saisons.get("ete"), saisons.get("hiver")
        if j - i >= 2 and isinstance(ete, PlagesHC) and isinstance(hiver, PlagesHC):
            sortie.append((periodes[i][0], PlagesSaisonnieres(ete, hiver)))
            i = j + 1
        else:
            sortie.append(periodes[i])
            i += 1
    return sortie
