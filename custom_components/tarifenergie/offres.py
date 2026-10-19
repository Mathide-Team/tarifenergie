"""Offres de marché : une offre-option par fichier YAML (issues #5, #6 et #343).

Règle de l'inventaire (#6) : **une offre-option = une issue = un fichier**. Le client ne
souscrit qu'une option (Base, Heures creuses, puis Tempo, heures super creuses, week-end…)
et le tarif dépend de l'option : chaque option est donc une offre distincte, avec sa
grille, comparée seule. Aucun fichier ne regroupe plusieurs options d'une même offre ;
un fichier qui le fait est refusé.

Le moteur ne sait encore lire que les offres-options **à prix fixe** (typologie CRE) aux
postes Base ou HP/HC ; les offres indexées (#350), les autres structures (#340 à #342) et
les prix dynamiques (#351) viendront avec leurs calendriers (``calendrier.py``).

Format (exemple : ``offres/la_bellenergie_prudence_hphc.yaml``) ::

    id: la_bellenergie_prudence_hphc      # nom du fichier, terminé par _<option>
    fournisseur: la bellenergie
    offre: Prudence
    option: hphc                          # base | hphc
    issue: 166                            # issue de l'offre-option (inventaire #6)
    type_prix: fixe                       # seul type supporté pour l'instant
    grille_du: 2026-08-01                 # date d'effet de la grille tarifaire
    duree_fixite_mois: 12
    source: https://…/grille.pdf          # fiche de référence (registre #27)
    territoire: enedis                    # facultatif : enedis (défaut) ou eld:<id> (#345)
    abonnement_mensuel_ttc: {6: 15.36, 9: 19.66, …}     # € TTC/mois par puissance
    kwh_ttc: {hp: 0.2106, hc: 0.1565}                    # € TTC/kWh, prix uniforme
    # ou kwh_ttc_par_puissance: {6: {hp: …, hc: …}, …}   # prix selon la puissance

Les prix sont TTC, en €/kWh (les grilles des fournisseurs sont en c€ TTC/kWh).
L'abonnement mensuel est converti en €/an (multiplié par 12, en ``Decimal`` exact). Les
puissances non listées rendent l'offre-option « indisponible » pour l'utilisateur
concerné, avec la raison, comme pour le TRV.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .const import PUISSANCES
from .modele import Grille, Grilles

DOSSIER_OFFRES = Path(__file__).parent / "offres"
TYPE_PRIX: tuple[str, ...] = ("fixe",)
# Option → postes tarifaires attendus dans la grille.
POSTES_OPTION: dict[str, frozenset[str]] = {
    "base": frozenset({"base"}),
    "hphc": frozenset({"hp", "hc"}),
}
LIBELLES_OPTION = {"base": "Base", "hphc": "Off-peak", "tempo": "Tempo"}
TERRITOIRE_PAR_DEFAUT = "enedis"
_TERRITOIRE = re.compile(r"^(enedis|eld:[a-z0-9_]+)$")
CHAMPS_OBLIGATOIRES = frozenset(
    {
        "id",
        "fournisseur",
        "offre",
        "option",
        "issue",
        "type_prix",
        "grille_du",
        "duree_fixite_mois",
        "source",
        "abonnement_mensuel_ttc",
    }
)
CHAMPS = CHAMPS_OBLIGATOIRES | {"territoire", "kwh_ttc", "kwh_ttc_par_puissance"}
MOIS_PAR_AN = Decimal("12")


class OffreInvalide(ValueError):
    """L'offre-option ne respecte pas le schéma. Le message donne le chemin de la valeur fautive."""


def _exiger(condition: bool, chemin: str, message: str) -> None:
    if not condition:
        raise OffreInvalide(f"{chemin} : {message}")


def _entier_positif(valeur: Any) -> bool:
    return isinstance(valeur, int) and not isinstance(valeur, bool) and valeur > 0


def _texte(d: dict[str, Any], cle: str) -> str:
    _exiger(isinstance(d.get(cle), str) and d[cle].strip() != "", f"offre.{cle}", "texte attendu")
    return d[cle]


def _decimal(valeur: Any, chemin: str) -> Decimal:
    _exiger(
        isinstance(valeur, (int, float)) and not isinstance(valeur, bool) and valeur > 0,
        chemin,
        "nombre positif attendu (€ TTC, c€ TTC/kWh convertis en €)",
    )
    return Decimal(str(valeur))


def _abonnements(d: dict[str, Any]) -> dict[int, Decimal]:
    """Mapping puissance (kVA) → montant (€ TTC/mois)."""
    chemin = "offre.abonnement_mensuel_ttc"
    brutes = d.get("abonnement_mensuel_ttc")
    _exiger(isinstance(brutes, dict) and brutes != {}, chemin, "mapping attendu")
    abonnements: dict[int, Decimal] = {}
    for puissance, montant in brutes.items():
        _exiger(
            _entier_positif(puissance) and puissance in PUISSANCES,
            chemin,
            f"puissance inconnue : {puissance} (attendues : {', '.join(map(str, PUISSANCES))} kVA)",
        )
        abonnements[puissance] = _decimal(montant, f"{chemin}[{puissance}]")
    return abonnements


def _prix(postes: Any, attendus: frozenset[str], chemin: str) -> dict[str, Decimal]:
    """Mapping poste → prix € TTC/kWh ; les postes doivent être exactement ceux de l'option."""
    _exiger(isinstance(postes, dict) and postes != {}, chemin, "mapping attendu")
    _exiger(
        set(postes) == attendus,
        chemin,
        f"postes attendus pour cette option : {', '.join(sorted(attendus))}",
    )
    return {poste: _decimal(montant, f"{chemin}.{poste}") for poste, montant in postes.items()}


def _grilles(donnees: dict[str, Any], ident: str, option: str, debut: date) -> Grilles:
    """Grilles de l'offre-option : abonnements mensuels x12, prix par poste et par puissance."""
    attendus = POSTES_OPTION[option]
    abonnements = _abonnements(donnees)
    uniforme = "kwh_ttc" in donnees
    _exiger(
        uniforme != ("kwh_ttc_par_puissance" in donnees),
        "offre",
        "kwh_ttc ou kwh_ttc_par_puissance attendu (exclusifs)",
    )
    if uniforme:
        prix = _prix(donnees["kwh_ttc"], attendus, "offre.kwh_ttc")
        par_puissance = dict.fromkeys(abonnements, prix)
    else:
        brutes = donnees["kwh_ttc_par_puissance"]
        _exiger(isinstance(brutes, dict) and brutes != {}, "offre.kwh_ttc_par_puissance", "mapping attendu")
        par_puissance = {}
        for puissance, postes in brutes.items():
            chemin = f"offre.kwh_ttc_par_puissance[{puissance}]"
            _exiger(puissance in abonnements, chemin, "prix donné sans abonnement à cette puissance")
            par_puissance[puissance] = _prix(postes, attendus, chemin)
    return Grilles(
        [
            Grille(ident, puissance, debut, None, abonnements[puissance] * MOIS_PAR_AN, prix)
            for puissance, prix in sorted(par_puissance.items())
        ]
    )


@dataclass(frozen=True)
class Offre:
    """Une offre-option de marché à prix fixe : une option, une issue, des grilles."""

    id: str
    fournisseur: str
    offre: str
    option: str
    issue: int
    grille_du: date
    duree_fixite_mois: int
    territoire: str
    grilles: Grilles

    @property
    def libelle(self) -> str:
        """« fournisseur Offre (Option) », pour les capteurs et le classement."""
        return f"{self.fournisseur} {self.offre} ({LIBELLES_OPTION[self.option]})"

    def raison_non_eligible(self, territoire: str) -> str | None:
        """Raison d'exclure l'offre-option pour un site desservi par ``territoire`` (#345)."""
        if self.territoire == territoire:
            return None
        return f"non disponible dans cette zone (offre {self.territoire}, site {territoire})"


def offre_depuis_dict(donnees: Any, ident: str) -> Offre:
    """Valide le contenu d'un fichier d'offre-option et le convertit en grilles."""
    _exiger(isinstance(donnees, dict), "offre", "mapping attendu")
    _exiger(
        "options" not in donnees,
        "offre.options",
        "un fichier = une offre-option (#343) : une option par fichier, pas de regroupement",
    )
    inconnus = set(donnees) - CHAMPS
    _exiger(not inconnus, "offre", f"champs inconnus : {', '.join(sorted(map(str, inconnus)))}")
    manquants = CHAMPS_OBLIGATOIRES - set(donnees)
    _exiger(not manquants, "offre", f"champs manquants : {', '.join(sorted(manquants))}")
    _exiger(donnees["id"] == ident, "offre.id", f"doit valoir « {ident} » (nom du fichier)")
    option = donnees["option"]
    _exiger(option in POSTES_OPTION, "offre.option", f"attendu : {', '.join(POSTES_OPTION)}")
    _exiger(
        ident.endswith(f"_{option}"),
        "offre.id",
        f"doit se terminer par « _{option} » (une offre-option par fichier)",
    )
    _exiger(_entier_positif(donnees["issue"]), "offre.issue", "numéro d'issue attendu (inventaire #6)")
    _exiger(donnees["type_prix"] in TYPE_PRIX, "offre.type_prix", f"attendu : {', '.join(TYPE_PRIX)}")
    _exiger(
        _entier_positif(donnees["duree_fixite_mois"]), "offre.duree_fixite_mois", "entier positif attendu"
    )
    grille_du = donnees["grille_du"]
    _exiger(isinstance(grille_du, date), "offre.grille_du", "date attendue (YYYY-MM-DD)")
    _texte(donnees, "source")
    territoire = donnees.get("territoire", TERRITOIRE_PAR_DEFAUT)
    _exiger(
        isinstance(territoire, str) and _TERRITOIRE.match(territoire) is not None,
        "offre.territoire",
        "enedis ou eld:<identifiant> attendu",
    )
    return Offre(
        ident,
        _texte(donnees, "fournisseur"),
        _texte(donnees, "offre"),
        option,
        donnees["issue"],
        grille_du,
        donnees["duree_fixite_mois"],
        territoire,
        _grilles(donnees, ident, option, grille_du),
    )


def charger_offre(chemin: Path) -> Offre:
    """Lit et valide un fichier YAML du dossier ``offres/``."""
    try:
        donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        raise OffreInvalide(f"{chemin.name} : YAML invalide ({err})") from None
    except (OSError, UnicodeDecodeError) as err:
        raise OffreInvalide(f"{chemin.name} : fichier illisible ({err})") from None
    try:
        return offre_depuis_dict(donnees, chemin.stem)
    except OffreInvalide as err:
        raise OffreInvalide(f"{chemin.name} : {err}") from None


def lire_offres(dossier: Path = DOSSIER_OFFRES) -> dict[str, Offre]:
    """Toutes les offres-options livrées avec l'intégration, indexées par identifiant.

    Deux fichiers ne peuvent pas documenter la même issue : une issue = une offre-option.
    """
    offres: dict[str, Offre] = {}
    issues: dict[int, str] = {}
    for chemin in sorted(dossier.glob("*.yaml")):
        offre = charger_offre(chemin)
        if offre.issue in issues:
            raise OffreInvalide(
                f"{chemin.name} : issue #{offre.issue} déjà utilisée par {issues[offre.issue]}"
                " (une issue = une offre-option)"
            )
        issues[offre.issue] = offre.id
        offres[offre.id] = offre
    return offres


def grilles_offres(offres: dict[str, Offre]) -> dict[str, Grilles]:
    """Grilles de chaque offre-option, indexées par son identifiant (clé de comparaison)."""
    return {ident: offre.grilles for ident, offre in offres.items()}


def exclusions(offres: dict[str, Offre], territoire: str) -> dict[str, str]:
    """Offres-options non éligibles pour un site desservi par ``territoire``, avec la raison."""
    return {
        ident: raison
        for ident, offre in offres.items()
        if (raison := offre.raison_non_eligible(territoire)) is not None
    }
