# Alice — de la V3 au laboratoire actuel

**Projet en développement — aperçu public au 3 novembre 2026.**

Ce dépôt présente maintenant deux étapes du projet : les extraits historiques
de la V3 et la nouvelle direction du laboratoire indépendant.

- **[Comprendre les progrès et la nouvelle direction](EVOLUTION.md)**
- **[Voir la version actuelle en développement et son code](version_actuelle/README.md)**
- **V3 historique :** les dossiers déjà présents à la racine restent conservés.

La partie actuelle est une sélection de cinq fichiers du laboratoire, accompagnée
d'un état des fonctions et des limites. Ce dépôt ne contient pas une installation
complète et ne se synchronise pas automatiquement avec le travail privé.

## La sélection historique V3

Alice est un projet personnel de compagnon vocal local, développé en français
sur Windows. Ce dépôt partage une **sélection de dix fichiers de code et de
tests** issus d'une ancienne version du projet.

Cette sélection reprend les fichiers déjà prévus pour le partage dans le dépôt
d'origine. Elle a été nettoyée et publiée le 3 novembre 2026 avec un historique
Git neuf. **Ce n'est ni le code complet d'Alice, ni un logiciel prêt à installer,
ni une description de sa configuration actuelle.**

## Ce que l'on peut consulter

| Dossier | Sujet |
| --- | --- |
| `voix/` | Service vocal Chatterbox local |
| `ecoute/` | Arrêt et nettoyage des processus Windows |
| `controle_alice/interface/` | Lecture audio progressive sous Windows |
| `controle_alice/tests/` | Exemples de tests de séparation entre interface et services |
| `outils/` | Affectation GPU et contrôle des priorités |
| `vision_alice/vision/hardware/` | Interrogation des cartes graphiques via DXGI |
| `vision_alice/vision/player/` | Détection de fenêtre et arrêt d'urgence |

Les [notes techniques](PIEGES.md) présentent quelques difficultés rencontrées.
Le [bilan de vérification](RESULTATS.md) précise les contrôles de cette publication.

## Limites

Ces fichiers sont des extraits : certains imports, services, modèles, fichiers
de configuration et ressources nécessaires à leur exécution ne sont pas inclus.
Les tests sont publiés comme exemples et ne constituent pas une suite autonome.
Il n'y a donc pas de commande d'installation complète dans cette copie.

Les noms et références personnelles présents dans les fichiers sélectionnés ont
été neutralisés. Aucun modèle, enregistrement vocal, capture d'écran, souvenir,
journal de conversation, sauvegarde privée ou ancien historique Git n'est inclus.

## Droits

La consultation publique du dépôt n'ajoute pas de licence générale de
réutilisation au code. Aucune nouvelle licence n'a été choisie pour cette copie.
Les bibliothèques et modèles mentionnés restent soumis à leurs propres licences ;
leurs fichiers ne sont pas redistribués ici.
