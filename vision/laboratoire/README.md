# Observation rendue du laboratoire

Implementation : `rendered_observation.py`. Tests : `tests/test_rendered_observation.py`.
Lecture DOM seulement ; aucune capture pixel, navigation ou action ajoutee.
Le navigateur et les gardes restent fournis par les appelants.

Depuis la racine du depot :
`laboratoire/.venv-vision/Scripts/python.exe -m pytest vision/laboratoire/tests/test_rendered_observation.py -q`

Import canonique : `vision.laboratoire.rendered_observation` depuis la racine Python.
Dependance conservee : `action_policy.validate_url` dans `laboratoire/scripts/`.
Le module canonique rend ce dossier accessible par un chemin relatif a sa racine,
y compris depuis le dossier vision, sans dupliquer ni deplacer la politique.
Facade temporaire : `laboratoire/scripts/rendered_observation.py` ajoute la racine
au chemin Python si necessaire et expose le meme objet module, helpers inclus.
Elle maintient public_navigation.py, brave_desktop_browser.py et
validation_rendered_observation.py. La retirer seulement apres migration de ces
consommateurs et verification de l'absence d'autres imports historiques.
Les tests ont ete deplaces ; leur ancien chemin n'est plus le point d'entree.

## Lecteurs UIA

Implementations : `native_uia_observer.py`, `native_uia_worker.py` et
`native_uia_snapshot.ps1`. Tests fictifs : `tests/test_native_uia_observer.py`
et `tests/test_native_uia_worker.py`. Aucun lecteur Windows reel dans ces tests.
Les commandes utilisent `vision/laboratoire/native_uia_snapshot.ps1` depuis
la racine Alice ; le protocole et le script PowerShell restent inchanges.
Imports canoniques : `vision.laboratoire.native_uia_observer` et
`vision.laboratoire.native_uia_worker`. Les deux facades dans
`laboratoire/scripts/` preservent le meme objet module et ses modifications.
Les conserver jusqu'a migration de `native_backend_factory.py`,
`validation_native_desktop.py` et `validation_native_notepad.py`.
Aucun autre appel du chemin PS1 n'a ete trouve dans les scripts et tests du
laboratoire : pas de relais PowerShell a l'ancien emplacement.

Depuis la racine du depot :
`laboratoire/.venv-vision/Scripts/python.exe -m pytest vision/laboratoire/tests/test_native_uia_observer.py vision/laboratoire/tests/test_native_uia_worker.py -q`

## Liens rendus

Implementation : `rendered_links.py`. Tests fictifs : `tests/test_rendered_links.py`.
Import canonique : `vision.laboratoire.rendered_links`. Dependances conservees :
`public_navigation.canonical_url` et `public_resources.origin`, accessibles dans
`laboratoire/scripts/` par un chemin relatif a la racine.
Facade temporaire : `laboratoire/scripts/rendered_links.py`, meme objet module
et memes helpers. La conserver jusqu'a migration de `brave_desktop_browser.py`,
`public_goal_navigation.py` et `public_link_navigation.py`.
Depuis la racine du depot :
`laboratoire/.venv-vision/Scripts/python.exe -m pytest vision/laboratoire/tests/test_rendered_links.py -q`
Les tests ont ete deplaces ; leur ancien chemin n'est plus le point d'entree.
Les sources locales des liens rendus n'etaient pas suivies avant migration :
le retour arriere demande aussi leur sauvegarde locale, indiquee dans SUIVI.md.

## Generateur de cas fictifs

Implementation : `vision_bench_cases.py`. Tests : `tests/test_vision_bench_cases.py`.
Import canonique : `vision.laboratoire.vision_bench_cases`.
Facade historique : `laboratoire/scripts/vision_bench_cases.py`, meme objet module,
helpers et patchs conserves pour runtime, OCR et observation_adapter.
Le generateur est deplace sans changement ; Pillow reste sa seule dependance externe.
Les tests utilisent et nettoient toujours `laboratoire/data/validation/validation_vision_cases_*`.
Depuis la racine du depot :
`laboratoire/.venv-vision/Scripts/python.exe -m pytest vision/laboratoire/tests/test_vision_bench_cases.py -q`
L'ancien chemin de test est retire. Retour arriere : revert du lot puis restaurer
le test ancien depuis la sauvegarde locale indiquee dans SUIVI.md (non suivi avant lot).

Les autres bancs vision ne sont pas encore migres.
L'installation originale, les donnees et les environnements restent inchanges.
Retour arriere observation : revert du commit de migration.
Pour UIA, les sources locales n'etaient pas suivies avant le deplacement :
restaurer aussi leur copie avant migration aux anciens emplacements, suivant
le SUIVI local. Un revert seul ne suffit pas. Ne pas toucher aux donnees.
