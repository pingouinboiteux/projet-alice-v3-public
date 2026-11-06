# Structure de la copie publique d'Alice

```text
README.md                 presentation et liens utiles
REGLES.md                 limites de contribution et workflow Git/GitHub
structure.md              carte des dossiers
scripts/                  migration technique (installation privee complete requise)
docs/
  etat/actuel.md          fonctions actives, mesures et limites
  pilotage/evolution.md   direction, priorites et criteres de passage
  technique/             pieges historiques et controles de publication
  provenance/            empreintes du code courant
laboratoire/
  README.md              carte des composants courants
  scripts/               dialogue, memoire, outils, voix et connexions
  src/alice/             ecoute, voix, materiel et services communs
  tests/                 tests logiciels et bancs de jugement
  personality/           consigne active neutralisee
  config/                selecteur memoire uniquement
historique/
  v3/                    anciens extraits : controle, ecoute, outils, vision, voix
  memoire_v5/             explication de la memoire originale, provenance, extraits
  laboratoire-20261103/   anciens extraits et leur provenance
```

Les README restent pres du code qu'ils expliquent. L'etat, l'evolution, les
pieges et les controles sont regroupes sous `docs/`, par fonction. Les fichiers
de provenance accompagnent les sources actuelles ou historiques correspondantes.

Les donnees et sauvegardes appartiennent a `data/` dans l'installation privee,
pas a cette copie publique. Ce dossier est volontairement absent : les souvenirs,
logs, rapports prives et sauvegardes ne doivent pas etre envoyes sur GitHub.
Les modules courants gardent leurs imports ; ce rangement ne modifie pas le code.

`historique/voix-abandonnees/` conserve la recette vocale D retiree du code courant.

Initiative et rythme : `laboratoire/scripts/conversation_initiative.py`,
`initiative_sequence.py`, `desktop_initiative.py`, `public_chat_selection.py`
et `stop_command.py`. Etat : [initiative](docs/technique/initiative-parole.md).

Contexte du stream : `laboratoire/scripts/public_scene.py`, `scene_context.py`,
`stream_recipient.py`, `desktop_recipient.py` ; [bilan](docs/technique/dialogue-stream.md).
Les dependances du parcours optionnel de notes se trouvent dans les modules
`desktop_note_validation.py`, `observer_*.py` et `vision_*.py` selectionnes.

Lecture Web et notes : [bilan](docs/technique/vision-web-notes.md) ; modules
`notes_*.py`, `note_operations.py`, `note_request.py`, `open_request.py`,
`web_*.py`, `public_navigation.py`, `public_resources.py`, `rendered_observation.py`
dans `laboratoire/scripts/`, tests correspondants dans `laboratoire/tests/`.
