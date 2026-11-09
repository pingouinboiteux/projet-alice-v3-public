# Missions de code bornées — état au 10 novembre 2026

Alice-Laboratoire peut recevoir une mission de programmation explicite dans sa
fenêtre locale. Le modèle travaille dans une copie dédiée sous
`laboratoire/atelier/missions/`. Le résultat n'est jamais appliqué automatiquement
au code actif.

| Commande | Résultat |
| --- | --- |
| `/faire <demande>` | Crée une mission dans l'atelier. |
| `/missions`, `/mission <id>` | Consulte le journal local. |
| `/reprendre <id>` | Relance une mission interrompue ou échouée. |
| `/faire fichier scripts/nom.py : <demande>` | Copie un module Python ordinaire du laboratoire. |
| `/appliquer <id>` | Affiche la différence, demande un accord, sauvegarde et remplace le module. |
| `/restaurer-code <id>` | Demande un accord et rétablit la version sauvegardée si le module n'a pas changé depuis. |

Le journal SQLite et les sauvegardes restent dans `laboratoire/data/`, exclu de
Git. La version active du module ne change qu'après redémarrage d'Alice. Les
messages publics Twitch et Discord ne peuvent pas lancer ces commandes.

Le journal identifie le processus qui exécute une mission. Ouvrir une seconde
fenêtre ne marque pas une mission encore active comme interrompue. Après un
arrêt, une mission de code inachevée peut être reprise explicitement. Si l'arrêt
survient pendant l'application ou la restauration, Alice compare les empreintes
du module actif et de sa sauvegarde avant de classer l'opération. Un état ambigu
devient `review` : aucun écrasement automatique, examen manuel puis nouvelle
mission.

## Frontière technique

Le lancement local utilise Codex `0.167.0` dans un runtime distinct. Son profil
Windows MXC donne l'écriture au dossier de mission, limite les lectures aux
fichiers nécessaires et coupe le réseau des commandes. Un contrôle avant mission
vérifie qu'une lecture interne réussit et qu'une lecture hors atelier échoue.
La clé du modèle local est retirée de l'environnement des commandes. La mission
est refusée si ce confinement ou cette version manque, ou si un jeu connu est
actif. Durée, nombre de fichiers et volume sont bornés ; les liens vers d'autres
emplacements sont refusés.

L'application d'une proposition est limitée à un fichier `.py` UTF-8 ordinaire,
directement dans `laboratoire/scripts`, de moins de 256 Kio. Les modules de
protection et de démarrage sont exclus. L'application vérifie l'empreinte du
fichier original, la syntaxe, une différence lisible et l'accord local. Une
sauvegarde sur le même disque facilite le retour arrière, sans protéger contre
une panne du disque. Une mission terminée ne prouve pas la justesse du code.
Alice ne dispose toujours pas d'un terminal libre ni d'un contrôle universel
du PC.

La sélection publique ne fournit ni modèle, ni runtime Codex, ni installation
Alice complète. Le script `laboratoire/scripts/installer_atelier_mxc.ps1` décrit
l'installation de la version épinglée ; il n'est pas lancé par GitHub Actions.
Les contrôles publics utilisent des données fictives, sans modèle, micro, son
ou réseau. La qualification réelle du confinement et du modèle reste propre
au PC où Alice est installée.

Sur ce PC, une reprise réelle et un dernier essai réel hors jeu ont produit le
fichier fictif attendu ; le moteur s'est arrêté ensuite. Les essais logiciels
ciblés couvrent aussi les arrêts pendant application et restauration, ainsi
qu'un fichier modifié entretemps. Une exception ponctuelle au refus de jeu a
provoqué un gel ressenti dans Cosmoteer alors que le compteur FPS n'a pas
détecté de chute suffisante : cet essai en jeu est **non validé**. Le refus
normal des missions pendant un jeu connu reste actif. Les rapports bruts et les
fichiers fictifs ne sont pas publiés.

Documentation du confinement : [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
et [permissions](https://learn.chatgpt.com/docs/permissions).
