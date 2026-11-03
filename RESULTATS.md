# Vérifications de la copie publique

Publication préparée le 3 novembre 2026.

- Sélection explicite de dix fichiers de code et de tests, prévue dans l'export
  public du dépôt d'origine.
- Exclusion des sauvegardes, mémoires, données de session, médias et archives.
- Neutralisation des références personnelles identifiées par le filtre d'export.
- Analyse syntaxique des neuf fichiers Python, sans les importer ni les exécuter.
- Contrôle de syntaxe et d'encodage ASCII du script PowerShell.
- Recherche de formats de clés privées, jetons, mots de passe, adresses e-mail
  et chemins personnels dans les fichiers destinés à la publication.
- Création d'un historique neuf : aucun ancien commit n'est transféré.

Ces contrôles concernent la préparation du dépôt public. Ils ne certifient pas
l'absence absolue de toute donnée sensible et ne constituent pas un test de
fonctionnement d'Alice. Aucun service, microphone ou mémoire réelle n'a été
ouvert par ces vérifications. Les anciennes mesures de performance ne sont pas
présentées ici comme des garanties actuelles.
