# Alice — compagnon vocal local

Alice est un prototype personnel de compagnon vocal en français pour Windows.
Son laboratoire sait dialoguer, mémoriser des échanges, lire certaines pages Web
et observer un écran à la demande ou à intervalles espacés. Il peut aussi
préparer une mission de code dans un atelier isolé. Son propriétaire
garde la main sur les actions qui modifient des documents ou diffusent une réponse.

Ce dépôt s'adresse aux personnes qui veulent **étudier le code et les choix du
projet**. Il contient une sélection publique mise à jour le **12 novembre 2026** : ce
n'est pas une installation prête à lancer. Les modèles, les voix personnelles,
les paramètres privés et certaines dépendances natives n'y figurent pas.

## Pour commencer

- [État des fonctions et limites](docs/etat/actuel.md) : ce qui a été mesuré sur
  l'installation d'origine et ce qui reste incertain.
- [Périmètre des protections](docs/etat/securite.md) : droits accordés à Alice,
  données lues et limites du mode protégé.
- [Carte du code](structure.md) et [index des documents](docs/INDEX.md).
- [Code courant du laboratoire](laboratoire/README.md) et
  [modifications de cette sélection](docs/technique/mise-a-jour-20261109.md).
- [Missions de code](docs/technique/missions-code.md) : commandes, protections
  et limites de l'atelier local, ainsi que le résultat de l'essai final.
- [Alice joue à Slay the Spire](docs/technique/slay-the-spire-20261112.md) :
  décisions du modèle, commentaires pendant la partie et limites mesurées.
- [Réparations fonctionnelles](docs/technique/fiabilisation-20261109.md) et
  [provenance des fichiers corrigés](docs/provenance/fiabilisation-20261109.json).
- [Direction du projet](docs/pilotage/evolution.md) et
  [provenance des fichiers](docs/provenance/mise-a-jour-20261109.json).

Les documents protégés ont un historique et une restauration. La recherche Web
utilise une fenêtre Brave isolée ; la lecture d'écran peut être demandée ou
surveiller un écran sélectionné. Les réponses publiques exigent un accord. Le
mode protégé refuse l'exécution libre de code, le navigateur personnel et les
lancements administrateur. Il ne confine pas Windows comme une machine virtuelle.
Les missions de code ont leur propre confinement Windows et ne peuvent modifier
un module du laboratoire qu'après revue et accord local.

Dans Slay the Spire, Alice choisit les actions parmi les options transmises par
un mod local. La conversation et les choix partagent le même modèle. Le lancement
depuis l'interface et le commentaire sont présents dans cette sélection ; leur
installation complète nécessite le jeu, les mods et les ressources privées.

Une fenêtre fictive sur un vrai écran a servi à vérifier lecture et voix. Un
ancien essai en jeu s'était interrompu après une chute des FPS pendant un
chargement. Depuis, deux essais silencieux de lecture passive et un essai avec
une phrase audible ont passé le garde FPS pendant des parties de TFT, sans gêne
ressentie par le propriétaire. Ces essais courts ne qualifient pas toutes les
parties ni tous les services simultanés : voir [les mesures](docs/etat/actuel.md).

## Vérification de cette sélection

Une [petite suite autonome](.github/workflows/smoke.yml) vérifie les versions de
notes, la livraison visuelle, l'humeur, la mémoire, la priorité visuelle et les
réponses Web et le pilotage du jeu avec des données fictives. Elle ne lance ni Alice, ni modèle, ni
microphone, ni navigateur. La
majorité des tests du projet exige encore des ressources absentes de ce dépôt.

La copie ne contient ni souvenirs, conversations privées, secrets, captures,
rapports bruts, ni historique Git privé. Les archives sous `historique/` sont
datées ; l'originale et le laboratoire restent distincts.

Aucune licence générale de réutilisation n'est jointe à cette publication.
Les modèles et dépendances conservent leurs propres licences.
