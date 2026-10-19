#!/usr/bin/env python3
"""Télécharge les grilles TRVE de la CRE dans custom_components/tarifenergie/tarifs/ (issue #2).

Les fichiers sont copiés sans modification ; les tests (tests/test_modele.py)
vérifient ensuite leur lecture et la continuité des périodes. À lancer à chaque
mouvement tarifaire (en général 1er février et 1er août), puis ouvrir une PR.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/{}"
FICHIERS = ("Option_Base.csv", "Option_HPHC.csv", "Option_Tempo.csv")
DOSSIER = Path(__file__).resolve().parent.parent / "custom_components/tarifenergie/tarifs"


def main() -> int:
    for nom in FICHIERS:
        requete = urllib.request.Request(URL.format(nom), headers={"User-Agent": "tarifenergie"})
        with urllib.request.urlopen(requete, timeout=60) as reponse:
            contenu = reponse.read()
        if not contenu.lstrip(b"\xef\xbb\xbf").startswith(b"DATE_DEBUT;"):
            print(f"{nom} : en-tête inattendu, fichier non remplacé", file=sys.stderr)
            return 1
        (DOSSIER / nom).write_bytes(contenu)
        print(f"{nom} : {contenu.count(b'\n')} lignes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
