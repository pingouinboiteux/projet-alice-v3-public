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
