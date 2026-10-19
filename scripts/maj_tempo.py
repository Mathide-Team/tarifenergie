#!/usr/bin/env python3
"""Ajoute les couleurs Tempo des jours passés à custom_components/tarifenergie/tarifs/tempo_couleurs.csv.

Issue #355 : données publiées (RTE), format stable : circuit « script », pas l'IA.

- Source : miroir public sans clé des couleurs RTE (jourtempo/tempo-historique), recoupé
  avec calendrier-tempo.fr ; la source officielle RTE demande un compte (docs/sources.md).
- Seuls les **jours passés** et le jour courant sont gardés : aucune couleur future.
- Une couleur déjà connue qui change (correction RTE) est signalée et appliquée.
- Les règles Tempo sont contrôlées (quotas, rouges en semaine de novembre à mars hors
  fériés, pas de blanc le dimanche) : au moindre écart, le fichier n'est pas modifié.

Usage : python3 scripts/maj_tempo.py   (puis ouvrir une PR vers dev)
"""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
import urllib.request
from datetime import date
from pathlib import Path

URL = "https://jourtempo.fr/api/v1/tempo-historique.csv"
RACINE = Path(__file__).resolve().parent.parent
MODULE = RACINE / "custom_components/tarifenergie/tempo.py"


def _tempo():
    """Charge tempo.py seul (sans le paquet de l'intégration, qui importe Home Assistant)."""
    spec = importlib.util.spec_from_file_location("tempo", MODULE)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["tempo"] = module  # requis par dataclasses
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def main() -> int:
    tempo = _tempo()
    fichier = tempo.FICHIER_COULEURS
    connues = tempo.lire_couleurs(fichier)
    requete = urllib.request.Request(URL, headers={"User-Agent": "tarifenergie"})
    with urllib.request.urlopen(requete, timeout=60) as reponse:
        texte = reponse.read().decode("utf-8")
    aujourd_hui = date.today()
    publiees: dict[date, str] = {}
    for ligne in csv.DictReader(io.StringIO(texte)):
        jour = date.fromisoformat(ligne["date"])
        if jour <= aujourd_hui and ligne["couleur"] in tempo.COULEURS:
            publiees[jour] = ligne["couleur"]
    corrections = {j: (c, publiees[j]) for j, c in connues.items() if j in publiees and publiees[j] != c}
    nouvelles = {j: c for j, c in publiees.items() if j not in connues}
    fusion = {**connues, **publiees}
    erreurs = tempo.verifier_regles(fusion)
    if erreurs:
        print("Règles Tempo non respectées, fichier inchangé :", *erreurs, sep="\n  ", file=sys.stderr)
        return 1
    for jour, (avant, apres) in sorted(corrections.items()):
        print(f"correction RTE : {jour} {avant} → {apres}")
    if not nouvelles and not corrections:
        print("aucun jour nouveau")
        return 0
    with fichier.open("w", encoding="utf-8", newline="") as sortie:
        sortie.write("date;couleur\n")
        for jour in sorted(fusion):
            sortie.write(f"{jour.isoformat()};{fusion[jour]}\n")
    print(f"{len(nouvelles)} jour(s) ajouté(s), jusqu'au {max(fusion).isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
