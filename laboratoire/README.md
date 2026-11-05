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
