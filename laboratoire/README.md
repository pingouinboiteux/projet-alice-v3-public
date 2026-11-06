# Code du laboratoire — instantané du 5 novembre 2026

| Dossier | Contenu publié |
| --- | --- |
| `scripts/` | Modules courants de dialogue, mémoire, outils, interface, voix et connexions ; scripts de campagnes anciennes exclus |
| `src/alice/` | Composants Python d'écoute, voix, matériel et configuration |
| `tests/` | Tests logiciels, bancs de jugement et banc adaptatif avec fiches fictives |
| `personality/` | Consigne active de personnalité, nom du propriétaire neutralisé |
| `config/` | Sélecteur du backend mémoire uniquement |

[Provenance et empreintes](../docs/provenance/laboratoire.json) : copies des chemins homonymes dans
le projet de travail, fins de ligne normalisées ; seules les références au nom
du propriétaire ont été remplacées par `Proprietaire` / `proprietaire`.
Les modules expérimentaux encore présents ne sont pas tous utilisés par le
lanceur : leur présence ne signifie pas leur activation.

Les configurations complètes, modèles, ponts binaires, environnements, données,
rapports bruts et anciennes campagnes ne sont pas inclus. Ne pas lancer les
bancs comme une installation autonome. Les tests présentés utilisent des données
fictives ; ils doivent rester isolés des souvenirs réels.

Les bancs de jugement proposent des variantes d'essai ; aucune n'est déclarée
validée ou active. Aucun entraînement automatique n'est lancé par cette publication.
Voir [l'état actuel](../docs/etat/actuel.md) et [les critères](../docs/pilotage/evolution.md).

`scripts/desktop_services.py` gere maintenant le demarrage et le nettoyage ;
`scripts/alice_desktop.py` conserve la boucle de conversation.

Les modules `adaptive_*_candidate.py` sont des experiences inactives, chargees
uniquement par une option explicite du banc. Leurs tests ne qualifient pas
leur comportement conversationnel.

Le [rappel de memoire](../docs/technique/rappel-memoire.md) utilise maintenant
le budget final avec schema, une priorite equilibree des sources et un lecteur
factuel avec identite/tutoiement explicites. Les sources restent intactes.
Les 485 tests reussis decrivent la suite locale : les ressources manquantes
et les bancs prives exclus empechent de la reproduire integralement ici.
Aucun banc ni jeu de questions issu de conversations privees n est publie.

## Initiative, rythme et interruption

`conversation_initiative.py` gere les occasions et pauses ;
`initiative_sequence.py` cadre les sujets courts ; `desktop_initiative.py`
garde le contexte public borne. `public_chat_selection.py` choisit dans les
rafales sans accumuler une dette. `stop_command.py`, les raccords d'ecoute et
la voix gerent l'interruption optionnelle. `validation_stop_asr.py` est un
banc synthetique sans microphone ni diffusion, necessitant l'installation locale.

La suite locale mesuree compte maintenant 594 tests. Les preuves brutes et les
campagnes modeles ne sont pas copiees. Voir [fonctionnement et limites](../docs/technique/initiative-parole.md).

## Dialogue du stream - novembre 2026

`stream_recipient.py` et `desktop_recipient.py` controlent l'attribution vocale.
`public_scene.py` et `scene_context.py` portent le contexte partage borne entre
Twitch et animation. La personnalite et `episode_protocol.py` assouplissent la
forme des reponses. [Etat, utilisation et limites](../docs/technique/dialogue-stream.md).
Les modules de validation vision importes par le parcours de notes optionnel
sont du code de demonstration, sans ressources ni donnees privees publiees.

## Lecture Web et notes naturelles

`notes_dialogue.py`, `notes_access.py`, `notes_storage.py` et `note_request.py`
portent les notes/listes locales. `open_request.py` controle les ouvertures.
`web_reader.py`, `web_passages.py`, `web_evidence.py` traitent la lecture ciblee ;
`public_navigation.py`, `public_resources.py`, `rendered_observation.py` bornent
le rendu public isole. [Fonctions et limites](../docs/technique/vision-web-notes.md).
