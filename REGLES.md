# Regles de travail sur Alice

Ces regles s'appliquent au projet local et a sa copie publique. Les demandes
explicites de le proprietaire priment ; les consignes locales precisent leur perimetre.

## Commencer une intervention

1. Lire `docs/etat/actuel.md` pour l'etat, puis `structure.md` pour choisir le composant.
2. Dans cette copie publique, lire aussi `laboratoire/README.md`. Les consignes
   de l installation privee ne sont pas toutes redistribuees.
3. Definir un objectif unique, ce qui reste hors perimetre et la verification
   qui permettra de declarer le travail termine. Ne pas ajouter de fonctionnalite
   opportuniste pendant une correction ou un rangement.
4. Chercher les noms avec `rg --files`, les fichiers avec `rg -l`, puis lire les
   fonctions concernees. Ne pas charger tous les fichiers et rapports.

## Sous-agents, modeles et economie de travail

Autorisation explicite de le proprietaire le05/11 : utiliser des sous-agents quand
cela apporte un gain utile, sans attendre une activation manuelle de sa part.

- Garder les taches courtes ou dependantes dans l'agent principal. Deleguer une
  recherche bornee, un controle independant ou un composant reellement separable.
- Choisir parmi les modeles effectivement disponibles : modele leger pour les
  controles mecaniques et recherches ciblees ; modele de code polyvalent pour
  l'implementation ; modele plus capable et effort accru si la difficulte ou
  les consequences le justifient. Augmenter la capacite en cas d'incertitude.
- Preferer un contexte court et explicite a la copie de toute la conversation.
  Donner objectif, chemins, limites, livrable attendu et criteres de fin.
- Ne pas multiplier les agents par principe : leurs tokens s'ajoutent et le
  parallelisme ne garantit pas un cout total inferieur. Pas de pourcentage
  d'economie annonce sans mesure. Respecter les limites de concurrence exposees.
- Eviter les modifications concurrentes sur les memes fichiers. Le principal
  relit et verifie les resultats ; chaque agent respecte les memes protections
  des souvenirs, secrets, tests et publications.
- Adapter le modele et l'effort quand les outils le permettent. Ne pas pretendre
  changer le modele principal d'un chat si aucun outil de session ne l'autorise.
  Utiliser la delegation disponible pour avancer sans attendre une manipulation
  manuelle inutile ; ne pas modifier en cachette la configuration globale.
- Ne pas changer les modeles locaux d'Alice au titre de cette preference : elle
  concerne les assistants de developpement, pas le moteur du produit.

## Modele d'Alice conserve

Decision explicite de le proprietaire : garder le modele actuel d'Alice. Diagnostiquer
les erreurs avec ce meme modele : consignes, contexte transmis, chaine logicielle
ou limite du LLM. Ne pas relancer de comparaison ou remplacer le modele a chaque
defaut. Un changement reste un dernier recours pour un probleme majeur etabli,
apres diagnostic et nouvelle decision explicite de le proprietaire. Une difficulte dans
un long debat philosophique ne suffit pas. Cette regle ne change pas le choix
des modeles des assistants de developpement autorise ci-dessus.

## Git et GitHub : branches, switch, merge, push

- Chaque nouvelle fonctionnalite, amelioration ou correction a sa propre branche
  `codex/<sujet>`. Pas de travail nouveau directement sur `main`.
- La demande de realiser ce travail autorise la creation de sa branche et le
  `git switch -c` initial. Un changement vers une autre branche sans rapport
  attend une demande explicite. Verifier la branche avant chaque modification.
- Examiner les changements deja presents avant le switch. Une branche nouvelle
  ne separe pas magiquement les modifications non commitees deja presentes :
  les conserver, les signaler et ne jamais les attribuer au nouveau travail.
- Ne jamais utiliser `git add .` ou `git add -A` dans ce projet. Selectionner
  explicitement les fichiers et relire le diff prepare.
- Un commit ne doit contenir que le travail concerne et ses controles ; ne pas
  creer de commit pour cette passe sans demande de l'utilisateur.
- **Merge et push uniquement sur demande explicite de l'utilisateur**, avec
  branche source, destination et contenu verifies. Une ancienne autorisation de
  publication n'autorise pas automatiquement toutes les publications futures.
- Pas de force-push, reset destructeur, nettoyage des fichiers non suivis ou
  reecriture de l'historique pour simplifier le travail.
- Git local, depot prive et selection publique GitHub sont des objets distincts.
  Ne jamais publier la racine privee comme si elle etait la selection publique.
- Avant toute publication : selection explicite, controle des secrets et donnees
  personnelles, puis verification du commit et de l'acces distant apres envoi.

## Organisation et limites techniques

- Code par responsabilite, donnees sous `data/`, documentation par sujet sous
  `docs/`. Respecter les implantations actives indiquees dans `structure.md`.
- Nouveaux rapports sous `data/validation/`, sauvegardes sous `data/sauvegardes/`,
  preparation publique sous `data/publication/` ; equivalents dans le laboratoire.
  Les anciens chemins restent valides tant qu'une migration dediee n'est pas testee.
- Ne pas melanger memoire documentaire (`docs/memoire/`) et souvenirs personnels
  (`data/` prive). Ne pas ranger du code executable dans les sauvegardes.
- Avant de deplacer du code : rechercher imports, lanceurs, configurations,
  tests et chemins relatifs. Decouper selon une responsabilite autonome, pas
  selon un nombre arbitraire de lignes ou une economie de tokens supposee.
- Chemins du code/configuration relatifs au projet ; PowerShell ASCII compatible
  Windows PowerShell 5.1. Pas de chemins personnels fixes dans le code nouveau.
- Ne pas lire un autre projet pour chercher ses consignes ou son implementation.

## Ne jamais faire pendant un test

- Ouvrir la memoire reelle : utiliser un profil `validation_`, puis nettoyer ses
  donnees. Ni microphone, ni diffusion audio, ni message externe sans autorisation.
- Modifier manuellement les souvenirs, exporter des secrets ou publier des
  conversations, voix personnelles, bases, journaux ou sauvegardes privees.
- Relancer un service, modifier le demarrage Windows ou deplacer des modeles
  pour un rangement documentaire. Conserver les ressources de retour arriere.
- Confondre un test logiciel reussi avec une preuve de comprehension du modele.
  Verifier l'instrument avant de conclure et appliquer les gardes propres a la
  campagne ; une exception FPS n'annule pas la garde RAM des validations.

## Terminer une etape

Verifier le comportement concerne et les risques introduits. Pour un rangement,
controler chemins, liens, conservation des fichiers et absence de changement
fonctionnel ; ne pas relancer des essais lourds sans raison. Mettre l'etat a jour
seulement apres controle reussi. Expliquer simplement ce qui change, la preuve,
les limites et ce qui reste a faire. Ne pas declarer termine ce qui reste incertain.
