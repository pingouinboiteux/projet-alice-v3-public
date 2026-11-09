# Alice — compagnon vocal local

Alice est un prototype personnel de compagnon vocal en français pour Windows.
Son laboratoire sait dialoguer, mémoriser des échanges, lire certaines pages Web
et observer un écran à la demande ou à intervalles espacés. Son propriétaire
garde la main sur les actions qui modifient des documents ou diffusent une réponse.

Ce dépôt s'adresse aux personnes qui veulent **étudier le code et les choix du
projet**. Il contient une sélection publique datée du **9 novembre 2026** : ce
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
- [Direction du projet](docs/pilotage/evolution.md) et
  [provenance des fichiers](docs/provenance/mise-a-jour-20261109.json).

Les documents protégés ont un historique et une restauration. La recherche Web
utilise une fenêtre Brave isolée ; la lecture d'écran peut être demandée ou
surveiller un écran sélectionné. Les réponses publiques exigent un accord. Le
mode protégé refuse l'exécution libre de code, le navigateur personnel et les
lancements administrateur. Il ne confine pas Windows comme une machine virtuelle.

Une fenêtre fictive sur un vrai écran a servi à vérifier lecture et voix. Dans
**cette version publiée**, la fluidité pendant une partie reste non qualifiée :
un ancien essai s'est interrompu après une chute des FPS pendant un chargement.
Les mesures et leurs réserves figurent dans [l'état actuel](docs/etat/actuel.md).

## Vérification de cette sélection

Une [petite suite autonome](.github/workflows/smoke.yml) vérifie les versions de
notes, la livraison visuelle et des garde-fous de réponse Web avec des données
fictives. Elle ne lance ni Alice, ni modèle, ni microphone, ni navigateur. La
majorité des tests du projet exige encore des ressources absentes de ce dépôt.

La copie ne contient ni souvenirs, conversations privées, secrets, captures,
rapports bruts, ni historique Git privé. Les archives sous `historique/` sont
datées ; l'originale et le laboratoire restent distincts.

Aucune licence générale de réutilisation n'est jointe à cette publication.
Les modèles et dépendances conservent leurs propres licences.
