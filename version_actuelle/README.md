# Version actuelle — en développement

Instantané public du 3 novembre 2026, issu du laboratoire indépendant.
**Extraits consultables, pas une distribution installable.**

## Ce qui est déjà raccordé

Le laboratoire dispose d'un dialogue local avec écoute et voix, d'une mémoire
épisodique privée, d'une bibliothèque locale, de pensées silencieuses bornées,
de souvenirs publics distincts par personne et plateforme et de sous-titres OBS.
Twitch est lu sans publication de texte ; les réponses peuvent passer par la
voix locale. Discord utilise son raccord vocal. Les entrées externes n'ont pas
accès aux actions locales ni aux souvenirs privés, même pour le propriétaire.

Les actions locales restent limitées et encadrées. Le routage des intentions
conserve des erreurs connues ; les contrôles et confirmations restent nécessaires.
Les vérifications de connexion ne valent pas qualification d'un stream complet.

## Recherche ouverte : lire fidèlement une archive

L'étape 1 de la mémoire est **non qualifiée**. Les sources entières sont
conservées ; les indices générés ne doivent pas réduire le contexte. Les
interactions relues restent historiques, sans autorité sur les outils.

| Mesure déjà consignée dans le projet | Résultat | Limite |
| --- | --- | --- |
| Candidat `scoped_typed` | 10 cas connus satisfaisants, puis 9/12 conversations nouvelles satisfaisantes | Trois réserves de portée, citation/contexte ou fin de permission ; non installé |
| Candidat `historical_context` | 4/6 sondages satisfaisants | Confusion permission/demande et ajout de précision chronologique ; non installé |
| Durée de ces lectures | Médianes 184,36 s sur 22 lectures et 180,355 s sur six sondages, respectivement | Lecture expérimentale d'archives, pas latence vocale ; lots différents, pas classement de vitesse |
| Dernier bilan logiciel de l'étape 1 | 199 tests logiciels passent | Ne valide ni le sens des réponses, ni la mémoire active, ni le dialogue complet |

Ces résultats sont une synthèse des mesures locales déjà documentées, pas de
nouveaux essais exécutés pour cette publication. Sources de rédaction :
`laboratoire/PROJET.md`, `laboratoire/docs/memoire-etape1-portee.txt` et
`laboratoire/docs/memoire-etape1-reglages.txt` dans l'installation de travail.
Les rapports bruts et conversations ne sont pas redistribués ; ces chiffres ne
constituent donc pas un benchmark reproductible depuis ce dépôt seul.

Les défauts de ton, répétitions, rectifications et interprétation ne sont pas
déclarés résolus. Aucun de ces résultats ne garantit une fiabilité générale.

## Lire le code publié

| Fichier | Rôle | Statut |
| --- | --- | --- |
| [remote_contracts.py](extraits/remote_contracts.py) | Validation des identités et paquets audio Discord | Module du raccord existant ; ne prouve pas à lui seul l'isolation des canaux |
| [capability_state.py](extraits/capability_state.py) | État technique réel des connexions transmis au dialogue | Module du dialogue existant |
| [memory_stage1_coverage.py](extraits/memory_stage1_coverage.py) | Contrats de lecture et validation de structure | Recherche, pas garantie de compréhension |
| [memory_stage1_interaction.py](extraits/memory_stage1_interaction.py) | Lecteur de référence des essais avec profils `validation_` et sources préservées | Recherche, distinct de la mémoire active |
| [memory_stage1_historical_context.py](extraits/memory_stage1_historical_context.py) | Contexte historique sans décision de validité opérationnelle | Candidat non retenu pour installation |

Ces cinq fichiers sont des copies du code de travail, pas une réécriture de
démonstration. La seule neutralisation textuelle remplace le nom du propriétaire
dans `capability_state.py`. Les fins de ligne sont normalisées en LF.
Les modules de transport, certains constructeurs de schémas, les modèles,
configurations et dépendances ne sont pas inclus : les lecteurs ne s'exécutent
pas seuls. Aucun service ou souvenir n'est démarré par cette publication.

Voir [la provenance des fichiers](PROVENANCE.md), [l'évolution](../EVOLUTION.md)
et [les contrôles de publication](../RESULTATS.md).
