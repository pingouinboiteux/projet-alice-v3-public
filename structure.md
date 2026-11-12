# Structure de la copie publique d'Alice

Mise à jour du 12 novembre 2026 : [état courant](docs/etat/actuel.md).

```text
README.md                 présentation et liens utiles
REGLES.md                 limites de contribution et travail Git/GitHub
structure.md              carte des dossiers
scripts/                  migration technique (installation privée complète requise)
docs/
  INDEX.md                index des documents
  etat/actuel.md          fonctions actives, mesures et limites
  etat/securite.md        périmètre des protections
  pilotage/evolution.md   direction, priorités et critères de passage
  technique/             pièges historiques et contrôles de publication
  provenance/            empreintes du code courant
laboratoire/
  README.md              carte des composants courants
  scripts/               dialogue, mémoire, outils, voix et connexions
  jeux/slay_spire/        agent, liaison, lanceur, journal et tests fictifs
  src/alice/             écoute, voix, matériel et services communs
  tests/                 tests logiciels et bancs de jugement
  personality/           consigne active neutralisée
  config/                sélecteur mémoire uniquement
historique/
  v3/                    anciens extraits : contrôle, écoute, outils, vision, voix
  memoire_v5/             explication de la mémoire originale, provenance, extraits
  laboratoire-20261103/   anciens extraits et leur provenance
```

Les README restent près du code qu'ils expliquent. L'état, l'évolution, les
pièges et les contrôles sont regroupés sous `docs/`, par fonction. Les fichiers
de provenance accompagnent les sources actuelles ou historiques correspondantes.

Les données et sauvegardes appartiennent à `data/` dans l'installation privée,
pas à cette copie publique. Ce dossier est volontairement absent : les souvenirs,
journaux, rapports privés et sauvegardes ne doivent pas être envoyés sur GitHub.
Les modules courants gardent leurs imports ; ce rangement ne modifie pas le code.

`historique/voix-abandonnees/` conserve la recette vocale D retirée du code courant.

Initiative et rythme : `laboratoire/scripts/conversation_initiative.py`,
`initiative_sequence.py`, `desktop_initiative.py`, `public_chat_selection.py`
et `stop_command.py`. État : [initiative](docs/technique/initiative-parole.md).

Contexte du stream : `laboratoire/scripts/public_scene.py`, `scene_context.py`,
`stream_recipient.py`, `desktop_recipient.py` ; [bilan](docs/technique/dialogue-stream.md).
Les dépendances du parcours optionnel de notes se trouvent dans les modules
`desktop_note_validation.py`, `observer_*.py` et `vision_*.py` sélectionnés.

Lecture Web et notes : [bilan](docs/technique/vision-web-notes.md) ; modules
`notes_*.py`, `note_operations.py`, `note_request.py`, `open_request.py`,
`web_*.py`, `public_navigation.py`, `public_resources.py`, `rendered_observation.py`
dans `laboratoire/scripts/`, tests correspondants dans `laboratoire/tests/`.

## Composants courants

- `controle/laboratoire/` : actions natives.
- `memoire/laboratoire/` : mémoire et sources.
- `interface/laboratoire/` : affichage, services, confirmations.
- `integrations/laboratoire/` : canaux et sous-titres.
- `vision/laboratoire/` : observation structurée déjà publiable.

Les synthèses plus anciennes restent des références datées. Les essais FPS/OCR et les données locales ne sont pas synchronisés.
