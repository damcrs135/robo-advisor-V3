# Ce qui change dans la V3

- **Questionnaire** : 35 questions (12 nouvelles : situation pro, stabilité des revenus, poids des crédits, priorité sécurité/performance, rendement espéré, ancienneté, fréquence des ordres, niveau déclaré, tirage 5 000 €/12 000 €, perte vs gain, fréquence de suivi, enveloppe souhaitée). Toutes alimentent le profil (`scoring.py`) ; les choix et oui/non sont obligatoires.
- **Âge** : désormais pris en compte (il ne servait à rien avant) : plafond à 4 dès 65 ans, 3 dès 75 ans.
- **ESG / exclusions** : le choix « article 8/9 » active le filtre ESG, et les secteurs cochés (armement, tabac, fossiles, alcool, aérien, nucléaire) sont retirés du portefeuille.
- **Bugs corrigés** : réponse manquante ou inconnue ne plante plus le calcul ; horizon inconnu ; portefeuille impossible à construire (trop d'exclusions) → repli automatique avec message ; obligations signalées à tort « frais non renseignés » ; case « oui » cochée par défaut sans que le client ait répondu.
- **Simulation** : graphique plus grand (480 px), axe en années calendaires, survol en euros.
- **PDF** (reportlab) : en-tête, chiffres clés, barres de notes, allocation, tableau par classe, courbe, risques et frais, adéquation, signature, annexe des réponses.
- **Excel** (sans macro) : 5 onglets mis en forme, barres de données, filtres, total, camembert et courbe natifs, prêt à imprimer.
- **Supprimé** : revue annuelle (fichier de l'an dernier, onglet caché « Données », macro VBA et `modele.xlsm`), rééquilibrage non utilisé, textes inutilisés.
- **Dépendance** : `fpdf2` remplacé par `reportlab` → `py -m pip install -r requirements.txt`.
