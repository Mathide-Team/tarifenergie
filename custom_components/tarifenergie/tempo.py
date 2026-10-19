"""Couleurs des jours Tempo : historique réel des jours passés et estimation des manques (#340, #355).

Principe (consigne du 19/10/2026, #340) : la simulation Tempo est une **estimation sur la
consommation réelle passée**, avec les **couleurs réelles** publiées par RTE. Ce n'est pas
une prévision : aucune couleur future n'est devinée pour annoncer un coût à venir.

Si la couleur d'un jour passé manque (fichier pas encore mis à jour, trou de la source),
elle est **estimée** en respectant les règles Tempo, et le jour est marqué « estimé ».

Règles (EDF, méthode de choix des jours de RTE ; voir ``docs/sources.md``) :

- saison du 1er septembre au 31 août : 22 jours rouges, 43 jours blancs, le reste bleu ;
- rouges : du 1er novembre au 31 mars, du lundi au vendredi, jamais un jour férié
  national, 5 consécutifs au plus (automatique : ni samedi, ni dimanche) ;
- blancs : toute l'année, sauf le dimanche ;
- exception connue : saison 2019-2020, 18 rouges et 47 blancs (décision de la CRE de
  remplacer les rouges par des blancs à partir du 19 mars 2020).

Estimation d'un manque, saison par saison :

1. nombre de rouges = espérance sur les jours manquants éligibles (fréquence historique
   des rouges à cette période de l'année, sur les saisons connues), arrondie et plafonnée
   par le quota restant de la saison ; idem pour les blancs (hors dimanche) ;
2. ces jours sont placés sur les jours manquants **les plus froids** (``rigueur`` : par
   exemple l'opposé de la température moyenne du jour) ; sans mesure de température, sur
   les jours de la période **climatologiquement la plus froide** (fréquence historique
   des rouges, puis des blancs) ;
3. les autres jours manquants sont bleus.

Python pur : aucun import Home Assistant (testable seul).
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

FICHIER_COULEURS = Path(__file__).parent / "tarifs" / "tempo_couleurs.csv"
BLEU, BLANC, ROUGE = "bleu", "blanc", "rouge"
COULEURS = (BLEU, BLANC, ROUGE)
QUOTA_ROUGE = 22
QUOTA_BLANC = 43
# Saison (année de début) → quotas réellement appliqués, quand ils diffèrent (décision CRE).
QUOTAS_EXCEPTIONNELS: dict[int, tuple[int, int]] = {2019: (18, 47)}
MAX_ROUGES_CONSECUTIFS = 5
# Lissage de la fréquence historique : ± 7 jours autour du même jour de saison.
FENETRE_LISSAGE = 7
HEURE_DEBUT_JOUR_TEMPO = 6  # une journée Tempo va de 6h à 6h le lendemain


class CouleursInvalides(ValueError):
    """Fichier de couleurs illisible ou contraire aux règles Tempo."""


class CouleurInconnue(LookupError):
    """Pas de couleur, réelle ni estimée, pour ce jour."""


def saison(jour: date) -> int:
    """Année de début de la saison Tempo du jour (1er septembre → 31 août)."""
    return jour.year if jour.month >= 9 else jour.year - 1


def _paques(annee: int) -> date:
    """Dimanche de Pâques (calendrier grégorien, algorithme de Meeus/Jones/Butcher)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    j = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * j) // 433
    mois = (h + j - 7 * m + 90) // 25
    return date(annee, mois, (h + j - 7 * m + 33 * mois + 19) % 32)


@lru_cache(maxsize=64)
def jours_feries(annee: int) -> frozenset[date]:
    """Jours fériés nationaux (hors fériés locaux d'Alsace-Moselle, qui peuvent être rouges)."""
    paques = _paques(annee)
    return frozenset(
        {
            date(annee, 1, 1),
            paques + timedelta(days=1),  # lundi de Pâques
            date(annee, 5, 1),
            date(annee, 5, 8),
            paques + timedelta(days=39),  # Ascension
            paques + timedelta(days=50),  # lundi de Pentecôte
            date(annee, 7, 14),
            date(annee, 8, 15),
            date(annee, 11, 1),
            date(annee, 11, 11),
            date(annee, 12, 25),
        }
    )


def rouge_possible(jour: date) -> bool:
    """Du 1er novembre au 31 mars, du lundi au vendredi, hors jours fériés nationaux."""
    hiver = jour.month >= 11 or jour.month <= 3
    return hiver and jour.weekday() < 5 and jour not in jours_feries(jour.year)


def blanc_possible(jour: date) -> bool:
    return jour.weekday() != 6


def quotas(annee_saison: int) -> tuple[int, int]:
    """(rouges, blancs) d'une saison."""
    return QUOTAS_EXCEPTIONNELS.get(annee_saison, (QUOTA_ROUGE, QUOTA_BLANC))


def lire_couleurs(chemin: Path = FICHIER_COULEURS) -> dict[date, str]:
    """Lit ``date;couleur`` (une ligne par jour, date ISO) ; refuse doublons et couleurs inconnues."""
    couleurs: dict[date, str] = {}
    with chemin.open(encoding="utf-8", newline="") as fichier:
        for numero, ligne in enumerate(csv.DictReader(fichier, delimiter=";"), start=2):
            try:
                jour = date.fromisoformat(ligne["date"])
            except (KeyError, TypeError, ValueError):
                raise CouleursInvalides(f"{chemin.name}, ligne {numero} : date illisible") from None
            couleur = ligne.get("couleur")
            if couleur not in COULEURS:
                raise CouleursInvalides(f"{chemin.name}, ligne {numero} : couleur inconnue {couleur!r}")
            if jour in couleurs:
                raise CouleursInvalides(f"{chemin.name}, ligne {numero} : {jour} en double")
            couleurs[jour] = couleur
    return couleurs


def verifier_regles(couleurs: Mapping[date, str]) -> list[str]:
    """Écarts aux règles Tempo (liste vide : conforme). Une saison incomplète est contrôlée en plafond."""
    erreurs: list[str] = []
    rouges: dict[int, int] = {}
    blancs: dict[int, int] = {}
    serie: list[date] = []
    for jour in sorted(couleurs):
        couleur = couleurs[jour]
        s = saison(jour)
        if couleur == ROUGE:
            rouges[s] = rouges.get(s, 0) + 1
            if not rouge_possible(jour):
                erreurs.append(f"{jour} : rouge interdit (week-end, jour férié ou hors novembre-mars)")
            serie = [*serie, jour] if serie and jour - serie[-1] == timedelta(days=1) else [jour]
            if len(serie) > MAX_ROUGES_CONSECUTIFS:
                erreurs.append(f"{jour} : plus de {MAX_ROUGES_CONSECUTIFS} rouges consécutifs")
        elif couleur == BLANC:
            blancs[s] = blancs.get(s, 0) + 1
            if not blanc_possible(jour):
                erreurs.append(f"{jour} : blanc interdit le dimanche")
    for s in sorted(set(rouges) | set(blancs)):
        quota_rouge, quota_blanc = quotas(s)
        if rouges.get(s, 0) > quota_rouge:
            erreurs.append(f"saison {s}-{s + 1} : {rouges[s]} rouges (quota {quota_rouge})")
        if blancs.get(s, 0) > quota_blanc:
            erreurs.append(f"saison {s}-{s + 1} : {blancs[s]} blancs (quota {quota_blanc})")
    return erreurs


def _rang_saison(jour: date) -> int:
    """Jour de la saison : 0 le 1er septembre."""
    return (jour - date(saison(jour), 9, 1)).days


@dataclass(frozen=True, slots=True)
class Climatologie:
    """Fréquence historique des rouges (jours éligibles) et des blancs (hors dimanche), lissée."""

    rouge: tuple[float, ...]
    blanc: tuple[float, ...]

    @classmethod
    def depuis(cls, historique: Mapping[date, str]) -> Climatologie:
        n = 366
        rouges, eligibles_r, blancs, eligibles_b = ([0] * n for _ in range(4))
        for jour, couleur in historique.items():
            rang = _rang_saison(jour)
            if rouge_possible(jour):
                eligibles_r[rang] += 1
                rouges[rang] += couleur == ROUGE
            if blanc_possible(jour) and couleur != ROUGE:
                eligibles_b[rang] += 1
                blancs[rang] += couleur == BLANC

        def lisser(num: list[int], den: list[int]) -> tuple[float, ...]:
            sortie = []
            for rang in range(n):
                fenetre = range(max(0, rang - FENETRE_LISSAGE), min(n, rang + FENETRE_LISSAGE + 1))
                total = sum(den[i] for i in fenetre)
                sortie.append(sum(num[i] for i in fenetre) / total if total else 0.0)
            return tuple(sortie)

        return cls(lisser(rouges, eligibles_r), lisser(blancs, eligibles_b))


@dataclass(frozen=True)
class CouleursTempo:
    """Couleur de chaque jour utile : réelle, ou estimée (``estimes``)."""

    couleurs: dict[date, str]
    estimes: frozenset[date] = field(default_factory=frozenset)

    def couleur(self, jour: date) -> str:
        try:
            return self.couleurs[jour]
        except KeyError:
            raise CouleurInconnue(f"couleur Tempo inconnue le {jour.isoformat()}") from None


def jour_tempo(debut: datetime) -> date:
    """Jour Tempo d'une heure : la veille pour les heures de 0h à 6h."""
    jour = debut.date()
    return jour if debut.hour >= HEURE_DEBUT_JOUR_TEMPO else jour - timedelta(days=1)


def jours_utiles(jours: Iterable[date]) -> set[date]:
    """Jours Tempo à connaître : la veille sert aux heures de 0h à 6h (journée de 6h à 6h)."""
    utiles: set[date] = set()
    for jour in jours:
        utiles.update((jour, jour - timedelta(days=1)))
    return utiles


def _plus_froids(
    candidats: list[date], frequence: tuple[float, ...], rigueur: Mapping[date, float]
) -> list[date]:
    """Le plus froid d'abord : rigueur mesurée, sinon période climatologiquement la plus froide."""

    def cle(jour: date) -> tuple[bool, float, float, date]:
        mesure = rigueur.get(jour)
        return (mesure is None, -(mesure or 0.0), -frequence[_rang_saison(jour)], jour)

    return sorted(candidats, key=cle)


def estimer(
    historique: Mapping[date, str],
    jours: Iterable[date],
    rigueur: Mapping[date, float] | None = None,
    climatologie: Climatologie | None = None,
) -> CouleursTempo:
    """Couleurs des ``jours`` : historique réel, et estimation des jours absents (voir le module).

    ``rigueur`` : plus la valeur est haute, plus le jour est froid (ex. ``-température``) ;
    sans valeur pour un jour, la fréquence historique sert de classement.
    """
    utiles = set(jours)
    connus = {j: historique[j] for j in utiles if j in historique}
    manquants = sorted(utiles - set(connus))
    if not manquants:
        return CouleursTempo(connus)
    clim = climatologie or Climatologie.depuis(historique)
    rigueur = rigueur or {}
    estimees: dict[date, str] = {}
    for s in sorted({saison(j) for j in manquants}):
        manquants_s = [j for j in manquants if saison(j) == s]
        connus_s = [c for j, c in historique.items() if saison(j) == s]
        quota_rouge, quota_blanc = quotas(s)
        reste_rouge = max(0, quota_rouge - connus_s.count(ROUGE))
        reste_blanc = max(0, quota_blanc - connus_s.count(BLANC))

        candidats_r = [j for j in manquants_s if rouge_possible(j)]
        attendus_r = round(sum(clim.rouge[_rang_saison(j)] for j in candidats_r))
        rouges = _plus_froids(candidats_r, clim.rouge, rigueur)[: min(reste_rouge, attendus_r)]
        estimees.update(dict.fromkeys(rouges, ROUGE))

        candidats_b = [j for j in manquants_s if blanc_possible(j) and j not in estimees]
        attendus_b = round(sum(clim.blanc[_rang_saison(j)] for j in candidats_b))
        blancs = _plus_froids(candidats_b, clim.blanc, rigueur)[: min(reste_blanc, attendus_b)]
        estimees.update(dict.fromkeys(blancs, BLANC))
        estimees.update({j: BLEU for j in manquants_s if j not in estimees})
    return CouleursTempo({**connus, **estimees}, frozenset(estimees))
