# Aggregator Service

But: Enrichissement, fusion et persistance des `DetectionEvent`. Fournit des APIs de requête et statistiques.

Endpoints principaux
- `POST /events` : reçoit un `DetectionEvent`, calcule la `zone` si manquante, et sauvegarde en SQLite.
- `GET /events?since=&zone=&priority=` : liste les événements (filtrage possible).
- `GET /stats` : agrégats simples par zone et par niveau de priorité.

Base de données
- SQLite local : `services/aggregator/data/events.db`.

Exécution locale
```bash
uvicorn services.aggregator.main:app --host 0.0.0.0 --port 8020
```

Exemple d'appel
```bash
curl -X POST http://localhost:8020/events -H "Content-Type: application/json" -d @event.json
curl http://localhost:8020/stats
```

Notes
- Le schéma stocke le JSON des bbox/detections pour simplicité. Les données sont conformes à `shared/schemas/events.py`.
- Le calcul de `zone` est heuristique et basé sur `shared/config/constants.MOROCCO_BBOX`.
