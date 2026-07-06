# Satellite Monitor Service

But: Récupère les TLE depuis SatNOGS, met en cache et calcule la position via SGP4 (Skyfield).

Endpoints principaux
- `GET /tle/{norad_id}` : retourne le TLE courant (cache) pour le NORAD id.
- `GET /position?satellite_id=&timestamp=` : calcule lat/lon/altitude pour un timestamp UTC.
- `POST /refresh-tle` : vide le cache.

Dépendances
- `skyfield`, `httpx`.

Exécution locale
```bash
uvicorn services.satellite_monitor.main:app --host 0.0.0.0 --port 8010
```

Exemple d'appel
```bash
curl http://localhost:8010/position?satellite_id=25544&timestamp=2026-07-06T12:00:00
```

Notes
- SatNOGS DB API est utilisée (`db.satnogs.org/api/satellites?norad_cat_id=`). La disponibilité dépend du réseau.
