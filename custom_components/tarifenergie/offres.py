"""Offres de marché : grilles tarifaires des fournisseurs en YAML (issues #5 et #6).

Chaque fichier ``offres/<id>.yaml`` décrit une offre d'électricité pour particuliers,
telle que publiée dans les grilles des fournisseurs (inventaire #6, une issue par
offre). Le moteur v0.2 ne sait lire que les offres **à prix fixe** (typologie CRE) ;
les offres indexées, dynamiques ou à coloration de jours (OctoTempo…) viendront plus
tard avec leurs structures propres.

Format YAML (exemple complet : ``offres/la_bellenergie_prudence.yaml``) ::

    id: la_bellenergie_prudence          # doit être le nom du fichier, sans extension
    fournisseur: la bellenergie
    offre: Prudence
    type_prix: fixe                      # seul type supporté en v0.2
    grille_du: 2026-08-01                 # date d'effet de la grille tarifaire
    duree_fixite_mois: 12
    source: https://…/grille.pdf         # fiche de référence (registre #27)
    options:
      base:
        abonnement_mensuel_ttc: {3: 11.63, 6: 15.36, …}     # € TTC/mois par puissance
        kwh_ttc_par_puissance: {3: {base: 0.1968}, …}         # c'→€ TTC/kWh par poste
      hphc:                              # option facultative (jamais en 3 kVA au TRV)
        abonnement_mensuel_ttc: {6: 15.36, …}
        kwh_ttc: {hp: 0.2106, hc: 0.1565}                     # prix uniforme
        # ou abonnement_annuel_ttc: {6: 190.36, …} pour une grille publiée en €/an

Les prix sont TTC, en €/kWh (les grilles des fournisseurs sont en c€ TTC/kWh).
L'abonnement mensuel est converti en €/an (multiplié par 12, en ``Decimal`` exact) ;
``abonnement_annuel_ttc`` (grilles publiées en €/an) est repris tel quel. Les
puissances non listées par une offre la rendent « indisponible » pour l'utilisateur
concerné, avec la raison, comme pour les options du TRV.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .const import PUISSANCES
from .modele import Grille, Grilles

_LOGGER = logging.getLogger(__name__)

DOSSIER_OFFRES = Path(__file__).parent / "offres"
TYPE_PRIX: tuple[str, ...] = ("fixe",)
POSTES = ("base", "hp", "hc")
MOIS_PAR_AN = Decimal("12")


class OffreInvalide(ValueError):
    """L'offre ne respecte pas le schéma. Le message donne le chemin de la valeur fautive."""


def _exiger(condition: bool, chemin: str, message: str) -> None:
    _LOGGER.debug("_exiger: entrée")
    if not condition:
        _LOGGER.debug("_exiger: lève une exception")
        raise OffreInvalide(f"{chemin} : {message}")
    _LOGGER.debug("_exiger: fin")


def _texte(d: dict[str, Any], cle: str, chemin: str) -> str:
    _LOGGER.debug("_texte: entrée")
    _exiger(isinstance(d.get(cle), str) and d[cle].strip() != "", chemin + f".{cle}", "texte attendu")
    _LOGGER.debug("_texte: sortie")
    return d[cle]


def _decimal(valeur: Any, chemin: str) -> Decimal:
    _LOGGER.debug("_decimal: entrée")
    _exiger(
        isinstance(valeur, (int, float)) and not isinstance(valeur, bool) and valeur > 0,
        chemin,
        "nombre positif attendu (€ TTC, c€ TTC/kWh convertis en €)",
    )
    _LOGGER.debug("_decimal: sortie")
    return Decimal(str(valeur))


def _puissances(d: dict[str, Any], chemin: str) -> dict[int, Decimal]:
    """Mapping puissance (kVA) → abonnement (€ TTC/an).

    ``abonnement_mensuel_ttc`` (multiplié par 12) ou ``abonnement_annuel_ttc``
    (tel quel, pour les grilles publiées en €/an : diviser par 12 ne tombe pas
    juste, ex. GEDIA 190,36 €/an), exclusifs.
    """
    _LOGGER.debug("_puissances: entrée")
    _exiger(
        not ("abonnement_mensuel_ttc" in d and "abonnement_annuel_ttc" in d),
        chemin,
        "abonnement_mensuel_ttc et abonnement_annuel_ttc sont exclusifs",
    )
    champ, facteur = (
        ("abonnement_annuel_ttc", Decimal(1))
        if "abonnement_annuel_ttc" in d
        else ("abonnement_mensuel_ttc", MOIS_PAR_AN)
    )
    brutes = d.get(champ)
    _exiger(isinstance(brutes, dict) and brutes != {}, f"{chemin}.{champ}", "mapping attendu")
    puissances: dict[int, Decimal] = {}
    for puissance, montant in brutes.items():
        _exiger(
            isinstance(puissance, int) and not isinstance(puissance, bool) and puissance in PUISSANCES,
            f"{chemin}.{champ}",
            f"puissance inconnue : {puissance} (attendues : {', '.join(map(str, PUISSANCES))} kVA)",
        )
        puissances[puissance] = _decimal(montant, f"{chemin}.{champ}[{puissance}]") * facteur
    _LOGGER.debug("_puissances: %s", puissances)
    return puissances


def _postes(d: dict[str, Any], chemin: str) -> dict[str, Decimal]:
    """Mapping poste (base / hp / hc) → prix € TTC/kWh."""
    _LOGGER.debug("_postes: entrée")
    brutes = d.get("kwh_ttc")
    _exiger(isinstance(brutes, dict) and brutes != {}, chemin + ".kwh_ttc", "mapping attendu")
    postes: dict[str, Decimal] = {}
    for poste, prix in brutes.items():
        _exiger(poste in POSTES, f"{chemin}.kwh_ttc", f"poste inconnu : {poste}")
        postes[poste] = _decimal(prix, f"{chemin}.kwh_ttc[{poste}]")
    _LOGGER.debug("_postes: %s", postes)
    return postes


def _grilles_option(
    donnees: dict[str, Any], chemin: str, cles: tuple[str, ...], debut: date
) -> dict[int, Grille]:
    """Grilles d'une option de l'offre : abonnements mensuels x12, prix par poste."""
    _LOGGER.debug("_grilles_option: entrée")
    abonnements = _puissances(donnees, chemin)
    grilles: dict[int, Grille] = {}
    if "kwh_ttc_par_puissance" in donnees:
        _exiger("kwh_ttc" not in donnees, chemin, "kwh_ttc et kwh_ttc_par_puissance sont exclusifs")
        par_puissance = donnees["kwh_ttc_par_puissance"]
        _exiger(isinstance(par_puissance, dict) and par_puissance != {}, chemin, "mapping attendu")
        for puissance, postes in par_puissance.items():
            _exiger(
                puissance in abonnements,
                f"{chemin}[{puissance}]",
                "prix donné sans abonnement à cette puissance",
            )
            _exiger(isinstance(postes, dict) and postes != {}, f"{chemin}[{puissance}]", "postes attendus")
            prix: dict[str, Decimal] = {}
            for poste, montant in postes.items():
                _exiger(poste in POSTES, f"{chemin}[{puissance}]", f"poste inconnu : {poste}")
                prix[poste] = _decimal(montant, f"{chemin}[{puissance}].{poste}")
            _exiger(
                set(prix) <= {"base"} or set(prix) == {"hp", "hc"},
                f"{chemin}[{puissance}]",
                "base OU hp+hc attendus",
            )
            grilles[puissance] = Grille(cles, puissance, debut, None, abonnements[puissance], prix)
    else:
        prix_uniforme = _postes(donnees, chemin)
        _exiger(
            set(prix_uniforme) <= {"base"} or set(prix_uniforme) == {"hp", "hc"},
            chemin,
            "base OU hp+hc attendus",
        )
        for puissance, abonnement in abonnements.items():
            grilles[puissance] = Grille(cles, puissance, debut, None, abonnement, prix_uniforme)
    _LOGGER.debug("_grilles_option: %s grille(s)", len(grilles))
    return grilles


@dataclass(frozen=True)
class Offre:
    """Une offre de marché à prix fixe, convertie en grilles par option."""

    id: str
    fournisseur: str
    offre: str
    grille_du: date
    duree_fixite_mois: int
    grilles: dict[str, Grilles]  # option du TRV ("base", "hphc") → Grilles

    def cles(self) -> list[str]:
        """Clés de comparaison : ``<id>:<option>`` (ex. ``la_bellenergie_prudence:hphc``)."""
        _LOGGER.debug("Offre.cles: entrée")
        _LOGGER.debug("Offre.cles: sortie")
        return [f"{self.id}:{option}" for option in sorted(self.grilles)]


def offre_depuis_dict(donnees: Any, ident: str) -> Offre:
    """Valide le contenu d'un fichier d'offre et le convertit en grilles."""
    _LOGGER.debug("offre_depuis_dict: entrée")
    _exiger(isinstance(donnees, dict), "offre", "mapping attendu")
    _exiger(donnees.get("id") == ident, "offre.id", f"doit valoir « {ident} » (nom du fichier)")
    _exiger(
        ":" not in ident,
        "offre.id",
        "le caractère « : » est réservé aux clés de comparaison « <id>:<option> »",
    )
    _exiger(donnees.get("type_prix") in TYPE_PRIX, "offre.type_prix", f"attendu : {', '.join(TYPE_PRIX)}")
    duree = donnees.get("duree_fixite_mois")
    _exiger(
        isinstance(duree, int) and not isinstance(duree, bool) and duree > 0,
        "offre.duree_fixite_mois",
        "entier positif attendu",
    )
    _exiger(
        donnees.get("grille_du") is not None and hasattr(donnees["grille_du"], "isoformat"),
        "offre.grille_du",
        "date attendue (YYYY-MM-DD)",
    )
    _texte(donnees, "source", "offre.source")
    options = donnees.get("options")
    _exiger(
        isinstance(options, dict) and set(options) <= {"base", "hphc"} and "base" in options,
        "offre.options",
        "base attendue, hphc facultative",
    )
    grilles: dict[str, Grilles] = {}
    for option in ("base", "hphc"):
        if option not in options:
            continue
        grilles_option = _grilles_option(
            options[option], f"offre.options.{option}", f"{ident}:{option}", donnees["grille_du"]
        )
        _exiger(grilles_option != {}, f"offre.options.{option}", "aucune puissance définie")
        grilles[option] = Grilles(tuple(grilles_option[p] for p in sorted(grilles_option)))
    _LOGGER.debug("offre_depuis_dict: sortie")
    return Offre(
        _texte(donnees, "id", "offre"),
        _texte(donnees, "fournisseur", "offre"),
        _texte(donnees, "offre", "offre"),
        donnees["grille_du"],
        duree,
        grilles,
    )


def charger_offre(chemin: Path) -> Offre:
    """Lit et valide un fichier YAML du dossier ``offres/``."""
    _LOGGER.debug("charger_offre: entrée")
    try:
        donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        _LOGGER.debug("charger_offre: %s : %s", type(err).__name__, err)
        _LOGGER.debug("charger_offre: lève une exception")
        raise OffreInvalide(f"{chemin.name} : YAML invalide ({err})") from None
    except (OSError, UnicodeDecodeError) as err:
        _LOGGER.debug("charger_offre: %s : %s", type(err).__name__, err)
        _LOGGER.debug("charger_offre: lève une exception")
        raise OffreInvalide(f"{chemin.name} : fichier illisible ({err})") from None
    try:
        _LOGGER.debug("charger_offre: sortie")
        return offre_depuis_dict(donnees, chemin.stem)
    except OffreInvalide as err:
        _LOGGER.debug("charger_offre: %s : %s", type(err).__name__, err)
        _LOGGER.debug("charger_offre: lève une exception")
        raise OffreInvalide(f"{chemin.name} : {err}") from None


def lire_offres(dossier: Path = DOSSIER_OFFRES) -> dict[str, Offre]:
    """Toutes les offres livrées avec l'intégration, indexées par identifiant."""
    _LOGGER.debug("lire_offres: entrée")
    offres: dict[str, Offre] = {}
    for chemin in sorted(dossier.glob("*.yaml")):
        offre = charger_offre(chemin)
        offres[offre.id] = offre
    _LOGGER.debug("lire_offres: %s offre(s) %s", len(offres), sorted(offres))
    return offres


def grilles_offres(offres: dict[str, Offre]) -> dict[str, Grilles]:
    """Grilles de toutes les offres, indexées par clé de comparaison ``<id>:<option>``."""
    _LOGGER.debug("grilles_offres: entrée")
    resultats: dict[str, Grilles] = {}
    for offre in offres.values():
        for option, grilles in offre.grilles.items():
            resultats[f"{offre.id}:{option}"] = grilles
    _LOGGER.debug("grilles_offres: %s grille(s) %s", len(resultats), sorted(resultats))
    return resultats
