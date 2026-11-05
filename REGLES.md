# Regles de contribution

Lire l'etat actuel, puis la carte du composant concerne. Un seul objectif par
intervention, avec un resultat verifiable et un perimetre explicite.

## Git et GitHub

- Une branche `codex/<sujet>` par fonctionnalite, amelioration ou correction.
- La demande de travail autorise la creation et le switch initial vers sa branche.
  Tout autre switch doit correspondre a une demande explicite.
- Examiner les modifications deja presentes : une nouvelle branche ne les isole
  pas automatiquement. Ne pas les ecraser ou les inclure dans un commit sans revue.
- Selectionner les fichiers explicitement ; pas de `git add .` global.
- Commit, merge et push sur demande de l'utilisateur ; verifier source,
  destination et diff. Pas de force-push ni de nettoyage destructeur implicite.
- Une autorisation de publication passee n'autorise pas les suivantes.
- Ne jamais pousser le projet prive entier vers ce depot public. Auditer la
  selection, les secrets et les donnees, puis verifier le resultat distant.

## Code, donnees et validation

Chercher les fichiers utiles, puis les fonctions utiles ; ne pas tout relire.
Separer par responsabilite, sans morceler artificiellement les petits modules.
Avant un deplacement, verifier imports, lanceurs, chemins et tests.
Documentation sous `docs/`, code dans son composant, donnees et sauvegardes sous
`data/` dans l'installation privee. Ne jamais publier ces donnees personnelles.

Tests avec profils fictifs `validation_`, jamais avec une memoire reelle.
Ne pas lancer de modele, de micro, de voix ou de publication externe pour un
simple rangement. Ne pas installer un candidat experimental non qualifie.
Un test logiciel vert ne prouve pas la comprehension du modele. Documenter
les mesures, leurs limites et les conditions de fin avant de passer a la suite.

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

