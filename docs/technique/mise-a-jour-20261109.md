# Mise à jour publique du 9 novembre 2026

Actualisation des sources publiables, des tests et des dépendances déplacées
dans les composants contrôle, mémoire, interface et intégrations. Les alias
historiques restent visibles. Les archives déjà publiques sont conservées.

## Changements

- Recherche et navigation publiques bornées, réponses fondées sur les sources.
- Documents protégés, versions, restauration et import/export de copies.
- Versions des notes avant remplacement ; refus si la copie préalable échoue.
- Refus du code libre, du navigateur personnel et d'un lancement administrateur.
- Confirmation publique contextualisée et annulation des accords obsolètes.
- Lecture d'écran, surveillance espacée et réactions adaptées au contexte.
- Raccords et tests des frontières mémoire, outils, interface et diffusion.

## Vérifications locales antérieures

Protections : 203 tests, puis 61 contrôles ciblés après la correction finale.
Ces groupes se recoupent : ne pas additionner les comptes. Vision et raccords :
119 tests ciblés. Le modèle réel a été testé sur six images fictives ; une
séquence OCR/compteur/modèle avec horloge simulée a vérifié trois apparitions.

Une vraie fenêtre fictive a ensuite permis de vérifier capture, interprétation,
compteur et trois phrases complètes. Cela ne prouve pas la compréhension de
tous les écrans. En partie, les essais sont restés incomplets : perte de fraîcheur
des mesures FPS, puis chute mesurée à environ 28 FPS et image de 0,8 seconde
pendant un chargement. La cause reste non établie ; les processus ont été arrêtés.
Les corrections du banc hors jeu ne constituent pas une correction prouvée du jeu.

## Frontière de publication

Sélection explicite : sources, tests fictifs et synthèses réécrites. Aucun dossier
de données, rapport brut, capture, modèle, environnement, secret ou historique
Git privé ajouté. Nom du propriétaire neutralisé comme dans les versions antérieures.

Les outils FPS, l'OCR local, les bancs de mouvement et les pilotes de validation
réelle restent exclus. Les extraits FPS déjà publics sont conservés dans leur
version antérieure. Certains imports et tests dépendent donc de modules locaux
non publiés : cette copie n'est pas une distribution autonome.

[Empreintes actualisées](../provenance/mise-a-jour-20261109.json). Le manifeste du
6 novembre reste historique et ne décrit pas les sources modifiées depuis.

## Contrôle de cette copie publique

Compilation syntaxique des sources sans import ni lancement de service, contrôle
des chemins sélectionnés, formats de secrets et empreintes. Sur la copie publique
neutralisée, 68 tests autonomes passent (documents, notes, livraison visuelle,
preuves Web et confirmations). Un premier groupe plus large avait 76 succès et
un échec d'import : `screen_ocr` reste local. Les contrôles d'interface qui le
chargent nécessitent cette dépendance privée et ne sont pas déclarés autonomes.
Aucun test n'a lancé modèle, microphone, voix ou connexion externe.
