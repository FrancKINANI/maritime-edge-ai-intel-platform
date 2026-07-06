# Data Ingestor Service

But: Interface pour rechercher et télécharger des produits Sentinel-1 depuis CDSE (Copernicus Data Space Ecosystem).

Fonctions principales
- `search_cdse_odata(...)` : wrapper réutilisant la logique Phase0 pour interroger l'API OData.
- `download_safe_product(...)` : téléchargement et extraction du `.SAFE` via le service zipper CDSE.

Authentification
- Fournir `CDSE_USERNAME` et `CDSE_PASSWORD` via `.env` ou variables d'environnement.

Exécution locale / usage
Ces fonctions sont appelées par l'orchestrateur (ex: `services/data-ingestor/main.py`) ou manuellement depuis Phase0.

Notes
- La logique robuste d'authentification et téléchargement est réutilisée depuis `phase0/scripts/download_scenes.py`.
