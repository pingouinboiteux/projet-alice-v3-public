# État au 12 novembre 2026

Le laboratoire et l'installation originale restent distincts. Cette sélection
publique expose le code publiable, sans les ressources privées de l'installation.

| Partie | Disponible ou mesuré | Limites |
| --- | --- | --- |
| Dialogue | Modèle Gemma actuel, contexte et mémoire séparés | Compréhension et cohérence imparfaites |
| Voix | Sopro, profil conservé, phrases complètes hors jeu et une phrase en jeu | Pas d'endurance complète |
| Web | Recherche Brave isolée, extraits de sources sans reformulation générée, navigation bornée | Précision imparfaite des sources, aucun compte personnel |
| Natif | Saisie bornée dans le Bloc-notes avec relecture | Pas de contrôle universel du PC |
| Documents | Espace dédié, versions, journal, copies texte importées/exportées | Même disque, aucune sauvegarde externe |
| Notes | Versions avant remplacement, restauration contrôlée | Pas de versions rétroactives |
| Public | Accord sur le contenu avant diffusion, annulation contrôlée | Capture par logiciels externes non contrôlée |
| Écran | Lecture locale, surveillance espacée et flux passif annulable | Erreurs possibles et événements brefs manqués |
| Sécurité | Code libre, navigateur personnel et entrée administrateur refusés | Contrôles applicatifs, pas de VM ni confinement OS complet |
| Missions de code | Atelier MXC local, reprise après interruption, proposition de module avec accord et restauration | Code limité à un dossier de mission ; résultat à vérifier, refus pendant un jeu connu |
| Slay the Spire | Choix des cartes et routes par le modèle local, commentaire, lancement depuis l'interface | Parties et essais courts seulement ; progression durable et voix avec le nouveau bouton à vérifier |

## Jeu solo

Le mod local transmet l'état du jeu et les actions possibles. Alice choisit
parmi ces actions, relit ses choix non obligatoires et peut en parler avec la
même session de modèle que la conversation. Une seule option est exécutée
automatiquement. La liaison locale authentifiée arrête l'agent si le modèle
ne répond plus. Les journaux et expériences restent sur le PC privé.

Le 12 novembre, le bouton de l'interface a ouvert le vrai jeu avec un seul
modèle. Alice a exécuté 44 actions jusqu'à l'étage 6, dont 30 décisions du modèle
relues et 14 actions obligatoires. Elle a corrigé trois choix lors de la relecture.
Deux commentaires ont été produits en texte. La partie a été interrompue pour
le test. Un essai vocal antérieur par le raccourci a été entendu sans gêne
signalée. Voir [le bilan technique](../technique/slay-the-spire-20261112.md).

## Lecture d'écran

Le lanceur de vision charge le projecteur local du même modèle. Un seul écran
est sélectionné. Les observations restent hors souvenirs et routeur d'actions :
le texte visible ne devient pas une commande. La fonction n'archive pas les images.

« Regarde mon écran » demande une lecture ; `/ecran surveille 2` sélectionne le
secondaire, `/ecran stop` et le bouton Calme arrêtent la surveillance.
Les réactions privées utilisent la voix ; les remarques passives restent écrites
dans un contexte public connu. Tout contenu visible peut être lu : arrêter la
vision avant d'afficher des informations privées.

Capture environ toutes les cinq secondes, analyse générale au plus toutes les
vingt secondes, au plus une remarque spontanée par minute. Trois apparitions
distinctes d'un texte de mort dans un jeu connu peuvent déclencher une taquinerie.
Un affichage continu ne compte qu'une fois. Ce n'est pas un compteur universel.

## Preuves et réserves

Sur une vraie fenêtre fictive : 35 % lu, fin de tâche annoncée, trois apparitions
comptées et trois phrases terminées. Le modèle a néanmoins inventé une barre de
progression dans sa description interne alors que seul le pourcentage était
montré. Sa réponse prononcée était correcte ; sa perception reste faillible.

Lors d'un premier essai en partie, TFT et un combat ont été reconnus. La qualification a été interrompue :
mesures FPS périmées lors d'un essai, puis chute d'environ 60 à 28 FPS sur trois
secondes pendant un chargement. Sa cause exacte reste à isoler. Les contrôles
hors jeu ne prouvaient pas que cette difficulté était résolue.

Après les réparations, deux essais de lecture passive ont été menés en partie
pendant 180 secondes chacun, sans son ni micro : neuf observations par essai,
garde FPS passée, minimum glissant de 59,59 puis 59,73 FPS, contre environ 60 FPS
sur les références respectives. Un essai supplémentaire de 60 secondes avec une
seule phrase audible a aussi passé le garde FPS : minimum glissant 59,90 FPS,
phrase entendue en entier, aucune gêne ressentie selon le propriétaire.
Les rapports bruts restent privés. Ces essais courts ne qualifient ni une session
longue avec tous les services, ni toutes les scènes de jeu.
