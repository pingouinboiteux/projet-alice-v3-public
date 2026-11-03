# Vérifications de la copie publique

Publication préparée le 3 novembre 2026.

- Sélection explicite de dix fichiers de code et de tests, prévue dans l'export
  public du dépôt d'origine.
- Exclusion des sauvegardes, mémoires, données de session, médias et archives.
- Neutralisation des références personnelles identifiées par le filtre d'export.
- Analyse syntaxique des quatorze fichiers Python, sans les importer ni les exécuter.
- Contrôle de syntaxe et d'encodage ASCII du script PowerShell.
- Recherche de formats de clés privées, jetons, mots de passe, adresses e-mail
  et chemins personnels dans les fichiers destinés à la publication.
- Création d'un historique neuf : aucun ancien commit n'est transféré.

## Ajout de la version actuelle — 3 novembre 2026

- Conservation des dix fichiers historiques V3 sans modification.
- Ajout de cinq extraits du laboratoire et d'une présentation de l'évolution.
- Comparaison des extraits avec les sources locales : seule neutralisation du
  nom du propriétaire dans `capability_state.py`, et fins de ligne normalisées.
- Relecture des cinq fichiers, contrôle des liens Markdown locaux et recherche
  des formats de secrets et références personnelles sur les 23 fichiers publiés.
- Empreintes des cinq extraits dans `version_actuelle/PROVENANCE.md`.
- Aucun essai de modèle, de voix ou de mémoire effectué pour cet ajout.

Les mesures du laboratoire sont rapportées avec leur portée et leurs limites ;
elles ne sont pas reproduites par cette vérification de publication.

Ces contrôles concernent la préparation du dépôt public. Ils ne certifient pas
l'absence absolue de toute donnée sensible et ne constituent pas un test de
fonctionnement d'Alice. Aucun service, microphone ou mémoire réelle n'a été
ouvert par ces vérifications. Les anciennes mesures de performance ne sont pas
présentées ici comme des garanties actuelles.
