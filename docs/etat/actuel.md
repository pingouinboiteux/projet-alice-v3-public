# Alice actuelle — 6 novembre 2026

L'installation originale et le laboratoire sont distincts. Le travail fonctionnel
sur l'originale est en pause ; les essais actuels concernent le laboratoire.
Ce dépôt expose son code, sans ses données privées ni ses ressources de modèles.

| Partie | État actuel | Limites |
| --- | --- | --- |
| Dialogue | Gemma 4 26B-A4B Q4_0, moteur llama.cpp b12020 | Compréhension et cohérence non garanties |
| Voix | Sopro, référence originale, français, FP32, 2 étapes ; choix conservé | Sibilance encore perceptible ; référence audio exclue |
| Mémoire | Backend `v5_context`, stockage épisodique et sources | Stocker, retrouver et comprendre sont trois propriétés distinctes ; aucune fiabilité générale revendiquée |
| Personnalité | Consignes expressives et franches conservées | Un prompt ne garantit pas un avis cohérent |
| Actions | Notes/listes et ouverture Web claires sans bouton ; autres confirmations conservees | Pas de controle general autonome du PC, erreurs d interpretation possibles |
| Twitch / Discord | Lecture Twitch et raccord vocal Discord ; contexte public séparé | Les entrées externes n'obtiennent pas de droits locaux ni de souvenirs privés |
| Initiative | Modes discussion/animation optionnels, stop vocal et selection du chat | Calme au demarrage ; rythme en stream encore a valider |
| Vision | Lecture HTTPS ciblee et rendu CSS/JavaScript public isole raccordes | Lecture partielle, sans compte/clic/jeu ni perception generale |

## Dialogue du stream ameliore ; reprise de la vision

Destinataire vocal avant generation, expression plus souple et scene publique
temporaire commune entre Twitch et animation. Les consignes locales publiques
sont explicites (`/scene` ou « Alice pour le stream »). Modele, voix et souvenirs
prives conserves. Dernier lot :170 tests logiciels locaux ;10 situations
comparatives de contexte. Controle regroupe avant publication :219 tests locaux
passes. Ces mesures ne prouvent pas une fiabilite generale.
[Fonctionnement, mesures et limites](../technique/dialogue-stream.md).

Lecture Web ciblee, observation publique rendue et notes/listes persistantes
raccordees au dialogue local. Ouverture et creation/remplacement de notes sans
bouton pour les demandes claires ; clarification en cas de manque ou ambiguite.
30/30 intentions notes,9/9 etapes reelles,580 tests logiciels locaux passes et1
saute. Pas de nouvel essai micro, de controle PC general, de compte ou de jeu.
[Fonctions, mesures et limites](../technique/vision-web-notes.md).
La suite de la vision conserve le modele et les gardes de validation.

Cette selection publique ne contient ni donnees privees, ni ressources, ni
rapports bruts. [Code et provenance](../../laboratoire/README.md).

## Migration technique locale du 5 novembre

Journaux, caches, sorties et rapports regroupes sous data dans l installation
privee ; anciens chemins conserves par jonctions Windows, sans double copie.
Controle commun des chemins audio adapte : 349 tests logiciels laboratoire
et 18 tests originaux passent apres migration. Profil Sopro original a 2 etapes
conserve. Aucun essai micro ou son en direct pendant cette migration.
Ces controles ne changent pas le bilan de jugement conversationnel ci-dessus.

Apres migration, le proprietaire a effectue un essai et confirme le fonctionnement.
Ce retour utilisateur complete les tests logiciels, sans garantir tous les usages.
