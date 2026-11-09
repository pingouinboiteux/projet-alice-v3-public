# Laboratoire Alice — sélection publique au 9 novembre 2026

Le point d'entrée local est `scripts/alice_desktop.py`. Les lanceurs `Alice.bat`
et `Alice-vision.bat` supposent une installation privée complète ; les ressources
nécessaires ne sont pas distribuées dans ce dépôt.

Les réparations de mémoire, d'humeur, de vision passive et de réponses Web sont
décrites dans le [bilan de fiabilisation](../docs/technique/fiabilisation-20261109.md).

- `scripts/protected_workspace.py` et `protected_dialogue.py` : documents versionnés.
- `scripts/note_versions.py` : historique et restauration des notes.
- `scripts/autonomy_policy.py` : refus de l'administration et du code libre.
- `scripts/screen_*.py` : capture, analyse et réactions (OCR local non publié).
- `scripts/search_*.py`, `brave_*.py`, `public_*navigation.py` : Web borné.
- [Interface](../interface/laboratoire) : widgets, confirmations, services.
- [Contrôle](../controle/laboratoire) : actions natives bornées.
- [Mémoire](../memoire/laboratoire) : stockage et lecture des sources.
- [Intégrations](../integrations/laboratoire) : frontières publiques et sous-titres.
- `src/alice/` : modules d'écoute, voix et matériel déjà sélectionnés.
- `tests/` : contrôles logiciels, distincts des campagnes réelles locales.

Les alias dans `scripts/` conservent les imports des composants déplacés.
Configurations complètes, modèles, médias, données et bancs privés sont absents.
Les tests publiés ne sont pas une suite autonome et ne doivent pas être raccordés
aux souvenirs réels. Aucun entraînement ni service n'est démarré par la publication.

[État actuel](../docs/etat/actuel.md) · [Changements](../docs/technique/mise-a-jour-20261109.md)
