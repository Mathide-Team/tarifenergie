"""Constantes de l'intégration tarifenergie."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "tarifenergie"

CONF_NOM: Final = "nom"
CONF_ENERGIE: Final = "entite_energie"
CONF_PUISSANCE: Final = "puissance"
CONF_OPTION: Final = "option_actuelle"
CONF_HEURES_CREUSES: Final = "heures_creuses"
# Téléinformation (#370) : index HC et HP du compteur (capteurs d'énergie cumulée),
# facultatifs ; s'ils sont donnés, les plages HC sont détectées et remplacent la saisie.
CONF_INDEX_HC: Final = "index_hc"
CONF_INDEX_HP: Final = "index_hp"
SOURCE_TELEINFO: Final = "teleinformation"
SOURCE_SAISIE: Final = "saisie"
# Gestionnaire de réseau du site : « enedis » ou « eld:<id> » (#345). Pas encore demandé
# par le config flow (#347) : les entrées existantes restent sur Enedis.
CONF_TERRITOIRE: Final = "territoire"
TERRITOIRE_PAR_DEFAUT: Final = "enedis"

NOM_PAR_DEFAUT: Final = "Électricité"
HEURES_CREUSES_PAR_DEFAUT: Final = "22:00-06:00"

OPTION_BASE: Final = "base"
OPTION_HPHC: Final = "hphc"
OPTION_TEMPO: Final = "tempo"
# Options du TRV : chacune est une offre-option distincte (#343).
OPTIONS: Final = (OPTION_BASE, OPTION_HPHC, OPTION_TEMPO)

# Puissances souscrites des tarifs Bleu résidentiels (kVA), voir tarifs/*.csv.
PUISSANCES: Final = (3, 6, 9, 12, 15, 18, 24, 30, 36)

# Fenêtre de comparaison : les 12 derniers mois de consommation réelle.
FENETRE: Final = timedelta(days=365)
# Les statistiques horaires changent au plus une fois par heure ; un calcul
# toutes les 6 h suffit pour un comparatif annuel.
INTERVALLE_MAJ: Final = timedelta(hours=6)
