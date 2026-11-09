# Périmètre des protections publiées

Le mode protégé encadre les **actions proposées à Alice dans l'application**.
Il vérifie la cible et la confirmation des modifications de documents, garde des
versions pour la restauration et limite la saisie native au parcours qualifié
dans le Bloc-notes. Il refuse les demandes de code libre, le navigateur
personnel et le lancement administrateur. Une réponse destinée à un canal
public demande un accord avant diffusion.

Ces contrôles ne sont pas un confinement de Windows. Alice fonctionne avec les
droits de sa session ; ce mode ne crée pas une machine virtuelle et ne contrôle
pas tous les processus, fichiers ou accès réseau du PC. Le versionnement est
sur le même disque : il aide à revenir sur une édition, sans remplacer une
sauvegarde externe.

Les [missions de code](../technique/missions-code.md) ajoutent une frontière
distincte : elles utilisent le confinement Windows MXC, vérifié avant chaque
exécution. Elles n'accordent pas un terminal libre à Alice. Les changements de
modules actifs exigent une différence lisible, un accord et une sauvegarde.

La recherche Web lit des pages publiques dans une fenêtre dédiée. Le contenu
d'une page est traité comme une donnée. La recherche interactive restitue les
extraits relevés et leurs sources : le code ne présente plus une reformulation
générée comme vérifiée. Une citation reste une parole de la source, pas une
preuve générale de vérité. La lecture d'écran peut
voir les informations affichées sur l'écran sélectionné ; il faut l'arrêter
avant d'afficher des données privées. Les images ne sont pas archivées par cette
fonction dans la version décrite ici.

La copie publique exclut souvenirs, voix personnelle, captures, secrets et
rapports bruts. Cette sélection ne permet pas de vérifier tous les parcours de
l'installation complète. Voir [l'état courant](actuel.md) et les
[contrôles de publication](../technique/mise-a-jour-20261109.md).
