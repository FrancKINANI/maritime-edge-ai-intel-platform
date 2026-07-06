# Sentinel Preprocessor Service

But: Calibrage, filtrage anti-speckle, conversion en dB, normalisation et découpage en tuiles `.npy` pour ingestion par le détecteur.

Endpoints principaux
- `POST /preprocess?safe_path=<path>&pipeline=<A|B|C|D>` : lance le pipeline demandé et renvoie un manifeste JSON des tuiles générées.
- `GET /pipelines` : liste les pipelines disponibles.
- `GET /health` : état du service.

Pipelines disponibles
- A: baseline (normalisation directe)
- B: calibration Sigma0
- C: Sigma0 + filtre Lee
- D: Sigma0 + filtre Lee + log dB + égalisation (valeur par défaut provisoire)

Important
- Le choix par défaut `PREPROCESSING_PIPELINE` est provisoire (valeur par défaut documentée: `D`). Le benchmark Phase 0 n'est pas encore tranché — ne pas considérer `D` comme définitif.
- La méthode de géoréférencement s'appuie sur les LUTs/GCPs validés dans `phase0/scripts/sar_preprocessing.py` (sans la gestion de bord non auditée).

Exécution locale
```bash
uvicorn services.sentinel_preprocessor.main:app --host 0.0.0.0 --port 8002
```

Exemple d'appel
```bash
curl -X POST "http://localhost:8002/preprocess" -d "safe_path=/data/scenes/SCENE.SAFE&pipeline=D"
```

Emplacement de sortie
- Par défaut les tuiles sont écrites dans `phase0/data/tiles/<scene>/<pipeline>/`.
