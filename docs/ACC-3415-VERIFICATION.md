# ACC-3415 — vérification sans jeu ni appareil

## Guards

Depuis la racine du dépôt :

```sh
python3 tools/check_no_game_content.py .
python3 tools/check_letsgo_content.py
python3 tools/check_no_secrets.py --history
python3 -m unittest discover -s tests -p 'test*guard*.py' -v
python3 -m unittest discover -s tests -p test_no_internal_infra.py -v
python3 -m unittest discover -s engine/tests -p test_run_host_checks_preconditions.py -v
```

Le scanner historique parcourt toutes les références locales, sans limite de 200 commits. La CI récupère l'historique complet (`fetch-depth: 0`). Les diagnostics ne reproduisent pas le contenu suspect. Les tests utilisent uniquement des chaînes et chemins synthétiques, jamais de vraies clés ni de contenu de jeu.

## Préparation des host checks

Un clone non préparé doit retourner **RC 2**, avant toute compilation, en nommant les entrées absentes et les commandes :

```sh
cd engine
python3 tools/fetch_sources.py
python3 tools/build_shared_android.py --jobs 2
python3 tools/run_host_checks.py
```

Le staging sans `--build` suffit pour les préconditions des contrôles hôte ; `--android` exige en plus le build Android indiqué par le diagnostic. Les compilateurs et bibliothèques restent des prérequis distincts : un contrôle sauté n'est jamais une validation.

## Mesures locales du 09/11/2026

- Base de travail : `4a03e174b2fb8b3583935626a4e11bf3ebfe2dcb`.
- Suite racine complète : 28 tests, RC 0, aucun skip ; inclut 4 tests de guards et 5 tests statiques de jalons.
- Guards ciblés : 4 tests, RC 0.
- Contrat de préparation : 2 tests, RC 0 ; chaque entrée manquante est simulée séparément, ainsi que le clone non préparé et le staging hôte sans build Android.
- Infrastructure interne : 1 test, RC 0 sur les fichiers suivis. Un dépôt temporaire séparé contenant une adresse RFC 1918 synthétique suivie produit le rouge attendu ; ce dépôt temporaire est supprimé, aucun leurre n'est ajouté au dépôt produit.
- Guards contenu courant : RC 0 ; secrets avec historique local complet : RC 0.

Les tests racine ne voient les nouveaux fichiers comme « suivis » qu'après inclusion dans l'index. Les manifests doivent être régénérés après cette inclusion et après toute instrumentation sous `engine/`.

## Limites et remise en revue

Aucun appareil, jeu, clé, firmware, APK applicatif complet ni release utilisé ou publié. Les marqueurs statiques ne constituent pas un essai Android. Les mutations indépendantes des 18 leurres restent à la QA.

Les PR de conformité #12/#13/#14 étaient encore ouvertes lors du contrôle du 09/11/2026. Rebase sur leur résultat requis avant revue si elles sont fusionnées ; ne pas présenter cette branche comme fondée sur leur résultat actuel. Validation QA puis approbation du Directeur technique conservées.
