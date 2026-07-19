# Phase Post-0 — Fine-Tuning YOLOv8n sur Sentinel-1

> Suite directe de la Phase 0. Le diagnostic est clos : **le zero-shot domain transfer échoue (mAP@0.5 = 0.0)**.
> Il faut **fine-tuner** le modèle sur les 3 321 annotations AIS réelles.

## Contenu du dossier

| Fichier | Description |
|---------|-------------|
| `colab_finetune_yolo.ipynb` | **Notebook Colab** — fine-tuning YOLOv8n, évaluation, export ONNX |
| `dataset_summary.json` | Métadonnées du dataset (1 544 images, 3 321 boxes) |
| `phase0_closure.md` | Document final de la Phase 0 — toutes les analyses |
| `regenerate_zip.sh` | Script pour régénérer le ZIP (nécessite les scripts dans `phase0/scripts/`) |

## Procédure

### 1. Régénérer le ZIP (optionnel)

Le ZIP est déjà dans `phase0/data/colab_export/maritime_dataset.zip` (311 MB).
Si besoin de le régénérer :

```bash
cd ..
uv run python phase0/scripts/export_colab_dataset.py
```

### 2. Upload sur Google Drive

```
maritime_dataset.zip  (311 MB)  →  Google Drive
```

### 3. Ouvrir le notebook dans Colab

```python
# 1. Aller sur https://colab.research.google.com
# 2. File → Upload Notebook → choisir colab_finetune_yolo.ipynb
# 3. Modifier ZIP_PATH dans la 2e cellule si nécessaire
# 4. Runtime → Change runtime type → T4 GPU
# 5. Run all cells (~2-4 heures)
```

### 4. Récupérer le modèle

Après fine-tuning, le notebook sauvegarde les modèles dans Google Drive :

- `yolov8n_maritime_v1.pt` (PyTorch)
- `yolov8n_maritime_v1.onnx` (ONNX FP32)
- `yolov8n_maritime_v1_int8.onnx` (ONNX INT8)

Les copier vers `shared/models/` dans ce projet.

### 5. Validation

```bash
cd ..
# Exemple avec la scène 2 (16/07/2026) — 1 534 tuiles annotées
uv run python phase0/scripts/benchmark_pipeline.py \
  --metadata phase0/data/tiles/S1D_..._9C83/D/metadata.json \
  --ground-truth phase0/data/annotations/S1D_..._9C83/labels/ \
  --model shared/models/yolov8n_maritime_v1.onnx
#                                    ^^^^^^^^^^^^^^^^^^^^^^^^
#                                    Remplacer par le modèle fine-tuné fraîchement exporté
```

## Rappel : Décisions clés de la Phase 0

- ✅ **CVAT ignoré** — les labels AIS sont utilisés directement comme Ground Truth
  (positions GPS fiables : 0% sur terre vérifié, précision < 10 m)
- ✅ **Pipeline D** recommandé pour le fine-tuning (σ⁰+Lee+Log+HistEq)
- ✅ **3 321 boxes** toutes en classe `vessel_AIS_confirmed` (pas de dark vessels détectés)
- ✅ **Dataset split** : 80/10/10 (train=1 235, val=154, test=155)

## Résultat attendu

Si le fine-tuning fonctionne :
- mAP@0.5 > 0.70 → **GO Phase 1** — déploiement microservices
- mAP@0.5 0.50–0.70 → **MARGINAL** — plus de données ou d'epochs
- mAP@0.5 < 0.50 → **STOP** — révision stratégique nécessaire

---

*Généré le 19 juillet 2026 — Projet Maritime Edge AI Platform*
