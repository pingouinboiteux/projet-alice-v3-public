# Alice actuelle — 5 novembre 2026

L'installation originale et le laboratoire sont distincts. Le travail fonctionnel
sur l'originale est en pause ; les essais actuels concernent le laboratoire.
Ce dépôt expose son code, sans ses données privées ni ses ressources de modèles.

| Partie | État actuel | Limites |
| --- | --- | --- |
| Dialogue | Gemma 4 26B-A4B Q4_0, moteur llama.cpp b12020 | Compréhension et cohérence non garanties |
| Voix | Sopro, référence originale, français, FP32, 2 étapes ; choix conservé | Sibilance encore perceptible ; référence audio exclue |
| Mémoire | Backend `v5_context`, stockage épisodique et sources | Stocker, retrouver et comprendre sont trois propriétés distinctes ; aucune fiabilité générale revendiquée |
| Personnalité | Consignes expressives et franches conservées | Un prompt ne garantit pas un avis cohérent |
| Actions | Outils locaux limités, confirmations et atelier encadré | Pas de contrôle général autonome du PC |
| Twitch / Discord | Lecture Twitch et raccord vocal Discord ; contexte public séparé | Les entrées externes n'obtiennent pas de droits locaux ni de souvenirs privés |
| Vision / initiative | Vision et parole spontanée non activées | Objectifs futurs, pas fonctions terminées |

## Chantier ouvert : un avis cohérent

Alice doit défendre une position fondée, résister à une simple pression et changer
d'avis lorsqu'un argument pertinent le justifie. Dire oui ou non systématiquement
serait un échec. Les phrases coupées sont reportées hors de ce chantier.

Première passe : 125 réponses fictives recensées, sans correction qualifiée.
Dernière passe : 188 réponses fictives, dont 20 relectures comparatives d'une même
entrée et 168 réponses traversant le dialogue complet. Comparaisons du contexte,
de la personnalité et de la préparation d'une position : progrès partiels sur
des choix concrets, mais dérive persistante dans les discussions longues.
**Aucune variante de ces essais n'a été installée.**

Les 347 tests logiciels de la première passe ont réussi dans l'environnement
local complet. Ce résultat ne valide pas le sens des réponses et n'a pas été
reproduit dans cette copie publique. La seconde passe n'a pas modifié le code
actif de dialogue. Les lots de validation réservés restent inutilisés.

Pour la voix retenue, quatre réponses du raccord réel à 2 étapes ont été
retranscrites complètement sans écrêtage PCM ; 36 tests ciblés ont passé.
Cela ne prouve pas l'absence de défaut perceptif ni une latence vocale constante.

Prochaine étape : préparer une comparaison avec un modèle témoin avant d'empiler
d'autres consignes. Aucun téléchargement ou entraînement lancé à ce titre.

Ces résultats résument les mesures locales consignées dans les états et bilans
du 5 novembre. Les rapports bruts ne sont pas redistribués : ce dépôt n'est pas
un benchmark reproductible à lui seul. [Code et provenance](../laboratoire/README.md).
