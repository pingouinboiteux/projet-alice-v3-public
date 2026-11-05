# Cycle de vie des services — 5 novembre 2026

Le demarrage et la fermeture sont maintenant dans `laboratoire/scripts/desktop_services.py`.
L'interface garde la conversation, les actions et les confirmations. Les constructeurs
sont fournis par le point d'entree ; importer le gestionnaire ne lance aucun service.
La session reste proprietaire de la voix. Les canaux acquis pendant la conversation
sont fermes avec les autres ressources en fin de session.

Le nettoyage poursuit les autres fermetures si une etape echoue. Une erreur de
creation de session produit aussi le signal de fin. Les erreurs restent signalees :
il s'agit de garantir les tentatives, pas le succes d'un service qui refuse de fermer.

La boucle conversationnelle est identique par comparaison AST. Cinq scenarios
simules donnent les memes appels et evenements avant/apres. 387 tests logiciels
passent, dont 29 nouveaux cas de cycle de vie. Le proprietaire a ensuite teste
Alice et confirme son fonctionnement avant d'autoriser la publication.
Aucun modele, souvenir prive ou enregistrement vocal n'est publie.
