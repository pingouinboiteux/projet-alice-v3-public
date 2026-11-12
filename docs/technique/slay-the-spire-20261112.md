# Alice joue à Slay the Spire : sélection du 12 novembre 2026

Cette sélection montre comment Alice joue à un jeu solo au tour par tour avec
le même modèle local que sa conversation. Le mod CommunicationMod transmet
l'état du jeu et les options permises. L'agent demande un choix au modèle,
fait relire les décisions non obligatoires, puis traduit l'option retenue en
commande du mod. Une option unique peut être exécutée automatiquement : le
journal distingue ces actions des décisions du modèle.

Le bouton **Jouer à Slay the Spire** de l'interface lance la liaison locale et
le jeu sur un profil séparé. Le commentaire reçoit des faits de jeu temporaires
et les choix récents. La liaison est authentifiée et l'agent s'arrête si le
modèle ne peut plus décider. Les données d'expérience sont locales et bornées ;
elles fournissent des observations des parties précédentes, sans réentraîner les
poids du modèle. Le code du jeu est dans
[laboratoire/jeux/slay_spire](../../laboratoire/jeux/slay_spire/README.md).

## Ce qui a été vérifié

- Les 31 tests ciblés du jeu, de la liaison et du bouton passent sur
  l'installation d'origine avec des données fictives. La suite autonome de ce
  dépôt vérifie également ces parcours sans jeu, modèle, micro ou voix.
- Le 11 novembre, un essai réel par le raccourci a produit 19 décisions du
  modèle, dont 14 cartes, et une phrase orale liée au jeu. Le propriétaire a
  entendu la phrase et n'a signalé aucune gêne.
- Le 12 novembre, un clic dans l'interface a ouvert le vrai jeu avec un seul
  modèle. Alice a exécuté 44 actions jusqu'à l'étage 6 : 30 décisions relues
  par le modèle, dont 3 corrigées à la seconde passe, et 14 actions obligatoires.
  Temps médian d'une décision : 1 177 ms. Deux commentaires ont été produits en
  texte sans son. Le jeu et les processus de validation ont été arrêtés
  proprement. Cette partie interrompue ne compte pas comme partie terminée.

Ces essais vérifient la provenance des choix et le raccordement de l'interface.
Ils ne prouvent pas encore une progression durable du niveau de jeu. Le micro
et la voix réelle avec le nouveau bouton, ainsi que les longues sessions, restent
à vérifier en usage normal. Le jeu, les mods, les modèles, les paramètres, les
journaux, les sauvegardes et les expériences privées ne sont pas publiés ici.
