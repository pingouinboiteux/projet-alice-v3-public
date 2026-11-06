# Dialogue et contexte du stream - 6 novembre 2026

Le modele Gemma, la voix Sopro et la memoire privee sont conserves. Cette
publication porte sur trois ameliorations mesurees, sans donnees utilisateur.

## Destinataire vocal

Avant reponse et memorisation, un classement distingue une adresse a Alice,
une parole destinee a autrui et une entree incertaine. Dans les deux derniers
cas Alice laisse la place avec une pause courte, sans desactiver l'animation.
Les demandes explicites de silence sont prises en compte. Une pause de18s
n'est pas un silence durable : le bouton stop et le mode calme restent utiles.
58/58 decisions parler/laisser passer sur un lot fictif cumule,57 etiquettes
exactes ;108 tests logiciels locaux. Un incident de verification du nettoyage
FPS a ete controle puis nettoye ; aucun arret de seuil signale dans ce lot.

## Expression naturelle

Les consignes n'imposent plus une observation, un avis, une justification et
un expose a presque chaque replique. Reagir, plaisanter, objecter ou developper
depend du propos. Aucun catalogue de repliques ni raccourcissement obligatoire.
12 paires fictives avec/sans ajustement,17 reponses supplementaires sur les
parcours installes et163 tests logiciels locaux. Gain qualitatif de naturel,
mais relances convenues, ton scolaire et limites de jugement restent presents.

## Scene publique commune

Twitch, la selection des messages et l'animation disposent d'une scene recente
en memoire vive :12 evenements,6000 caracteres,300 secondes au plus. Chaque
evenement garde son auteur, son origine et son destinataire. Seuls les messages
Twitch deja admis, les reponses publiques completement livrees et les consignes
locales explicitement partagees y entrent. La mention Alice reste necessaire.
Discord reste separe. Aucun historique local, souvenir prive ou pensee interne
n'est copie dans cette scene ; aucun nouvel acces aux outils n'est accorde.

Pour guider l'animation, dire « Alice pour le stream » suivi de la consigne,
ou ecrire `/scene ...`. En mode calme, cette commande ne declenche pas la parole.
Elle ne passe pas dans le routeur d'actions ni la memoire privee. Une parole
locale ordinaire n'est pas publiee automatiquement. La transcription doit
rester correcte pour reconnaitre le prefixe vocal.

Les propositions perimees sont invalidees. Une interruption ou deconnexion
pendant lecture ne doit pas reinscrire une ancienne reponse comme livree.
Reset, oubli accepte et fermeture nettoient la scene. La TTL de cette scene
ne supprime pas l'historique public durable preexistant de chaque auteur.

10 situations comparatives distinctes,37 reponses avec reprises,170 tests
logiciels dans la phase. Controle de regression regroupe avant publication :
219 tests locaux passes (incluant destinataire, contexte public et memoire V5).
References entre interventions et auteurs mieux suivis ;
une action seulement envisagee est encore parfois prise pour un fait etabli.
Une consigne supplementaire n'ameliorait pas ce cas et a ete ecartee. Pas de
qualification de longue soiree, de jugement global ou de tous les cas de debat.

## Portee de cette copie

Les nombres de tests concernent l'installation locale et des suites qui se
recoupent : ne pas les additionner comme autant de tests distincts. Les bancs
modeles, rapports bruts, ressources, enregistrements et souvenirs sont exclus.
La copie publique reste documentaire, pas une distribution installable.

L'interface inclut deja un parcours optionnel de validation de notes. Ses
dependances de code absentes de la precedente copie sont incluses pour garder
les imports lisibles ; cela n'active ni vision generale ni manipulation libre.
Les essais vision/observateur ont valide des parcours limites sur demonstration
et notes TiddlyWiki, sans commande de jeu ni raccord au dialogue ordinaire.
La suite demandee est de reprendre la branche vision. Les gardes FPS/RAM des
validations restent en place ; aucune garantie d'absence de ralentissement.
