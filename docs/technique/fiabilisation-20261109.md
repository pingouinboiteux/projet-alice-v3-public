# Fiabilisation du laboratoire — 9 novembre 2026

Cette sélection ajoute les réparations de code qui étaient déjà vérifiées dans
le laboratoire local mais absentes de la première branche documentaire. Le
modèle, la voix et la séparation entre laboratoire et installation originale
ne changent pas. Les essais utilisent des profils `validation_` fictifs ; les
rapports d'écran et de jeu restent privés.

## Corrections

- **Humeur :** le moteur seul n'interprète plus une expression hostile dans le
  texte comme une attaque adressée à Alice. Le dialogue actif demande au modèle
  de distinguer attaque directe, négation et citation dans son appel de
  classification déjà existant. Une réponse manquante reste neutre. Sur trois
  cas avec le modèle installé, deux phrases niées ou citées sont restées calmes
  et une attaque directe a produit l'état « vexée ».
- **Vision passive :** la requête au moteur local passe en flux annulable. Quand
  une demande de dialogue arrive, l'observation passive peut fermer ce flux et
  écarter son résultat. Avec une image fictive et le moteur installé, le retard
  ajouté à la demande simultanée est passé d'environ 1,34 à 0,75 seconde. Le
  premier fragment du flux peut encore retarder brièvement la réponse ; ce
  chiffre n'est pas une garantie de délai maximal.
- **Web :** la recherche interactive répond avec les extraits relevés dans les
  pages et leurs sources, sans prononcer de reformulation générée. Le module de
  synthèse, conservé pour étude hors parcours interactif, rejette maintenant un
  nombre absent des citations associées. Cela évite le cas « 42 places » devenu
  « 99 places ». Un texte cité peut encore être faux ou incomplet.
- **Mémoire :** une sélection vide n'efface plus les états ou le journal. Un
  marqueur de reprise accompagne l'oubli et la correction quand plusieurs
  stockages doivent être nettoyés. Une réponse produite reste en attente jusqu'à
  la fin de la parole ; après interruption ou arrêt, l'archive indique que le
  texte entendu est inconnu. La liste des échanges est bornée et signale une
  archive illisible sans perdre les autres. Les émotions et intentions passent
  par des méthodes du stockage.

## Vérifications et limites

Les tests fictifs du noyau mémoire, des épisodes, de la mémoire persistante, du
transport visuel et du Web passent localement. Une phrase fictive a été
prononcée puis retrouvée dans l'archive après redémarrage, sans micro ni souvenir
personnel. Deux essais silencieux et un essai vocal court pendant des parties de
TFT ont passé le garde FPS ; le propriétaire n'a ressenti aucune gêne. Les
chiffres détaillés sont dans [l'état actuel](../etat/actuel.md).

La [CI autonome](../../.github/workflows/smoke.yml) couvre un sous-ensemble sans
modèle ni ressources privées. Elle ne prouve ni la compréhension générale
d'Alice, ni l'absence de ralentissement dans toute partie, ni l'exactitude de
toute source Web. Les empreintes des fichiers corrigés sont dans le
[manifeste de provenance](../provenance/fiabilisation-20261109.json).
