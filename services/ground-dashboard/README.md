# Ground Dashboard (Streamlit)

But: Interface opérateur contenant trois modes : Upload, Satellite Query, Monitoring.

Modes
- Upload : téléversement de `.npy` et appel au `Detector`.
- Satellite Query : interroge `Satellite Monitor` pour la position d'un satellite.
- Continuous Monitoring : récupère `stats` et `events` depuis `Aggregator`.

Configuration
- `DETECTOR_URL`, `SATMON_URL`, `AGGREGATOR_URL` peuvent être configurées via variables d'environnement.

Exécution locale
```bash
streamlit run services.ground_dashboard.app:main --server.port 8050
```

Exemple d'usage
- Ouvrir `http://localhost:8050` et sélectionner le mode dans la barre latérale.
