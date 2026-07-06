# Detector Service

But: Wrapper FastAPI autour des modèles YOLOv8 ONNX quantifiés (INT8) pour détecter des navires dans des tuiles pré-traitées.

Endpoints principaux
- `POST /detect` : envoie une tuile `.npy` en base64 ou un chemin `tile_path` et reçoit un `DetectionEvent`.
- `GET /health` : état du service et chargement des modèles.

Modèles
- Placer les fichiers ONNX INT8 dans `shared/models/` et monter ce volume dans le container Docker.
- Noms par défaut : définis dans `shared/config/constants.py` (`DETECTOR_MODEL`, `SEGMENTER_MODEL`).

Exécution locale
- Via uvicorn :
```bash
uvicorn services.detector.main:app --host 0.0.0.0 --port 8001
```

Exemple d'appel
```bash
curl -X POST http://localhost:8001/detect -H "Content-Type: application/json" -d '{"tile_path":"/data/tiles/scene_tile0001.npy"}'
```

Notes
- Le service charge les modèles ONNX au démarrage pour éviter des reloads par requête.
- Le résultat retourné suit le schéma `DetectionEvent` (voir `shared/schemas/events.py`).
