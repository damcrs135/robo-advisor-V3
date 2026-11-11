# Robo-advisor patrimonial — M2 Banque-Finance

Site de conseil **simulé** (aucun argent investi) pour des clients de 100 k€ à 1 M€ : questionnaire → profil → portefeuille (actions et obligations en titres vifs) → simulation Monte Carlo → explication par IA → Excel + PDF Français et anglais.

Installation et mise en ligne : voir **GUIDE_INSTALLATION.md**.

## Fichiers (section 4.2 du cahier des charges)

| Fichier | Responsable | Contenu |
| --- | --- | --- |
| app.py, textes.py | Damien | Le site (10 étapes), tous les textes FR/EN |
| questionnaire.py, scoring.py, livrable_pdf.py | Peter | 23 questions, calcul du profil, revue annuelle, déclaration d'adéquation |
| regles.py, livrable_excel.py, llm.py, vba/MiseEnForme.bas | Amina | Profils et contraintes, enveloppes, construction, justifications, Excel, macro, IA |
| analytics.py, telecharger_prix.py | Aly | Cours, indicateurs, stress tests, corrélations, rééquilibrage |
| simulation.py | Haochen | Monte Carlo 10 000 trajectoires, 60/40, impact des frais |
| data/univers.csv | Aly + Haochen | 30 ETF/ETC + fonds euros + 1 SCPI + 2 fonds actifs |
| tests/ | chacun | 797 tests pytest |

Le contrat de la section 4.3 est respecté : mêmes noms de fonctions, mêmes entrées, mêmes sorties. Certaines fonctions acceptent des paramètres **optionnels** en plus (ex. `horizon` et `zone` pour `construire_portefeuille`, nécessaires à la règle SCPI et à la préférence géographique) et certaines sorties contiennent des clés **en plus** (ex. `alertes` dans le profil, `perf_5a` dans les indicateurs). Rien de ce qui est dans le contrat n'a changé.

## État des données — à compléter avant le 21 novembre

Dans `data/univers.csv`, les ISIN, noms, frais, encours, dates de création, modes de réplication, tickers et éligibilités PEA ont été relevés en ligne le 7 novembre 2026 (justETF, extraETF, Fortuneo, fiches émetteurs : lien dans la colonne `source`). Les descriptions sont rédigées par nous. Tout ce qui n'a pas pu être vérifié est marqué **TODO**, laissé vide plutôt qu'inventé :

| Colonne | Lignes en TODO | Où trouver |
| --- | --- | --- |
| `sri` | 32 / 34 | Section « Indicateur de risque » du DIC de chaque fonds (site de l'émetteur) |
| `sfdr` | 31 / 34 | DIC ou prospectus (« article 6 / 8 / 9 ») |
| `label_isr` | 33 / 34 | Liste des fonds labellisés sur lelabelisr.fr |
| `pea` | 3 | DIC / page de l'émetteur (EUSRI, WAT, GREAL) |
| `ticker_yahoo` | 2 | Rempli par `telecharger_prix.py --maj-univers` (fonds actifs) |
| `ter` (SCPI) | 1 | DIC Sofidy (frais de souscription et de gestion d'Immorente) |

Points signalés dans la colonne `remarques` :
- **MEUD** : 0,07 % sur extraETF contre 0,02 % de frais de gestion affichés par Fortuneo → trancher avec le DIC.
- **WSRI** (2024) et **GEU3C** (2023) ont moins de 5 ans d'historique ; **GREAL** a moins de 500 M€ d'encours (critères de la section 5.3) : gardés faute de mieux, à remplacer si l'équipe trouve un équivalent.
- **EUED** (obligations ultra-courtes ESG) sert de monétaire durable alors que ce n'est pas un fonds monétaire au sens strict.
- **Fonds en euros** : taux moyen 2025 du marché (2,65 %, France Assureurs / ACPR), pas celui d'un contrat précis. **SCPI** : taux de distribution 2025 d'Immorente (5,00 %).

## Hypothèses de la simulation (Haochen)

Source : Amundi Investment Institute, *Capital Market Assumptions — H2 update*, août 2026, horizon 10 ans (lien dans `simulation.py`). Les chiffres ont été lus dans l'extraction texte du PDF : **les recontrôler dans le tableau original**, en particulier la ligne immobilier coté (ambiguë). Les correspondances approximatives (thématiques, obligations 1-3 ans, SCPI, fonds patrimonial) sont marquées dans `CORRESPONDANCE`.

## Points à trancher par l'équipe

1. **SRI maximum de la grille 5.2.** D'après les seuils de volatilité du règlement PRIIPs (codés dans `regles.estimer_sri`), un portefeuille à 15-18 % de volatilité correspond à un SRI de 4, pas de 6. Les SRI max 5 et 6 des profils Dynamique et Offensif ne sont donc jamais contraignants. À corriger dans la grille ou à justifier à l'oral.
2. **Volatilité visée.** Avec les hypothèses Amundi et une corrélation de 1 (borne prudente), les 5 portefeuilles standard tombent dans leur fourchette (4,3 % · 7,6 % · 10,5 % · 13,1 % · 15,0 %). À recontrôler avec les cours réels : le site affiche un message si la volatilité historique sort de la fourchette.
3. **Frais de la « gestion traditionnelle »** (impact des frais, section 5.4) : le curseur part de 1,5 %, valeur de démonstration sans source. Trouver une source (étude AMF, rapport annuel d'un assureur…) et mettre à jour `ter_trad` dans `app.py`.
4. **Ce qui n'est pas fait** : frontière efficiente (bonus de Haochen) et envoi par e-mail (option de la section 5.5).
5. Le clic sur « Valider mes réponses » n'est pas couvert par les tests automatiques (limite de l'outil de test de Streamlit) : il est à vérifier à la main lors du test d'assemblage.
