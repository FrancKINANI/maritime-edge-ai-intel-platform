# Deployment Guide

This document describes how to deploy the Maritime Edge AI Intelligence
Platform in a real environment (dedicated server, VPS, or company site).

The platform is delivered as a set of **Docker containers** orchestrated with
**Docker Compose**. There are two compose files:

| File | Purpose | External dependencies |
|------|---------|-----------------------|
| `docker-compose.yml` | Production stack (6 services + Redis) | Copernicus CDSE + Global Fishing Watch API |
| `docker-compose.demo.yml` | Self-contained demo stack (no API keys required) | None |

---

## 1. Prerequisites

| Requirement | Minimum |
|-------------|---------|
| OS | Linux (Ubuntu 22.04+ / Debian 12+ recommended) |
| Docker Engine | 20.10+ (tested with 24.x–29.x) |
| Docker Compose plugin | v2.0+ |
| RAM | 8 GB (16 GB recommended) |
| Disk | 30 GB free (Sentinel-1 scenes and tiles are large) |
| CPU | 4 cores (8 recommended) |

Optional but recommended: **Nginx** or **Caddy** as a reverse proxy for TLS.

### Accounts needed for production mode

- [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) account
  (free) → `CDSE_USERNAME` / `CDSE_PASSWORD`
- [Global Fishing Watch](https://globalfishingwatch.org/our-apis/) API token
  (free tier) → `GFW_API_TOKEN`
- Optional: Sentinel Hub credentials (`SENTINEL_HUB_CLIENT_ID` /
  `SENTINEL_HUB_CLIENT_SECRET`) as a fallback source.

---

## 2. Getting the code

```bash
git clone https://github.com/FrancKINANI/maritime-edge-ai-intel-platform.git
cd maritime-edge-ai-intel-platform
```

### Model weights

The detection model files (`shared/models/*.onnx`) are **git-ignored** (they
are several MB and versioned outside the repository). Copy them into
`shared/models/` before building the detector image:

```bash
mkdir -p shared/models
# Place your .onnx files here, e.g.:
#   yolov8n_mrssd_int8.onnx   (main vessel detector)
cp /path/to/your/models/*.onnx shared/models/
```

The detector expects at least `yolov8n_mrssd_int8.onnx`.

---

## 3. Configuration

```bash
cp .env.example .env
nano .env   # fill in your credentials
```

| Variable | Required | Description |
|----------|----------|-------------|
| `CDSE_USERNAME` | Yes (prod) | Copernicus Data Space account email |
| `CDSE_PASSWORD` | Yes (prod) | Copernicus Data Space account password |
| `GFW_API_TOKEN` | For GFW features | Global Fishing Watch JWT token |
| `SENTINEL_HUB_CLIENT_ID` | No | Sentinel Hub client id (fallback) |
| `SENTINEL_HUB_CLIENT_SECRET` | No | Sentinel Hub client secret |
| `REDIS_URL` | No | Defaults to `redis://redis:6379` |
| `DATABASE_URL` | No | Defaults to `sqlite:///./maritime_intel.db` |
| `REGION_BBOX` | No | Default AOI: `lon_min,lat_min,lon_max,lat_max` |

Never commit the real `.env` file.

---

## 4. Building & starting (production)

```bash
# Build all images (base + 6 services)
docker compose build

# Start everything in the background
docker compose up -d

# Follow logs
docker compose logs -f

# Stop / restart / remove
docker compose down
docker compose restart <service>
```

### Verify health

```bash
curl http://localhost:8000/health   # sentinel-preprocessor
curl http://localhost:8001/health   # data-ingestor
curl http://localhost:8002/health   # aggregator
curl http://localhost:8003/health   # detector
curl http://localhost:8004/health   # satellite-monitor
docker compose ps                    # shows health status of all services
```

The dashboard is available at **http://localhost:8501**.

---

## 5. Service matrix

| Service | Port (host) | Purpose |
|---------|-------------|---------|
| `redis` | — (internal) | Shared cache / pub-sub |
| `data-ingestor` | 8001 | Sentinel-1 product search & download (CDSE) |
| `sentinel-preprocessor` | 8000 | SAR calibration, filtering, tiling, georeferencing |
| `detector` | 8003 | YOLOv8 ONNX inference on tiles |
| `satellite-monitor` | 8004 | TLE / SGP4 satellite position computation |
| `aggregator` | 8002 | Event enrichment, zone classification, persistence |
| `ground-dashboard` | 8501 | Streamlit operator UI (3 modes) |

### Dashboard modes

1. **Upload** — upload `.npy` tiles or `.SAFE` / `.tiff` products for detection.
2. **Satellite Query** — query a satellite position by NORAD ID
   (e.g. Sentinel-1A `39634`).
3. **Continuous Monitoring** — live detection events with filters
   (`since`, `zone`, `priority`).

---

## 6. Data volumes

| Volume | Mount | Content |
|--------|-------|---------|
| `tiles-volume` | `/data/tiles` | 512×512 preprocessed tiles (`.npy`) |
| `scenes-volume` | `/data/scenes` | Raw Sentinel-1 `.SAFE` products |

Volumes are Docker named volumes: they survive container recreation and are
shared between services. To back them up:

```bash
docker run --rm -v maritime-intelligence-platform_tiles-volume:/data -v $(pwd):/backup \
  alpine tar czf /backup/tiles.tar.gz -C /data .
```

---

## 7. Exposing the dashboard securely (reverse proxy)

The platform is designed for **trusted networks**. For public exposure, put it
behind TLS + authentication.

### Nginx example

```nginx
server {
    listen 443 ssl;
    server_name maritime.example.com;

    ssl_certificate     /etc/letsencrypt/live/maritime.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/maritime.example.com/privkey.pem;

    # Ground dashboard (Streamlit)
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Backend APIs (restrict access)
    location /api/ {
        # Require Basic Auth or an SSO layer here
        auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://127.0.0.1:8003/;
    }
}
```

### Firewall

Only expose `443` (HTTPS) and, if strictly required, `8501`. Keep service
ports (`8000`–`8004`) bound to `127.0.0.1`:

```yaml
ports:
  - "127.0.0.1:8003:8000"
```

### systemd unit (optional, auto-start)

```ini
[Unit]
Description=Maritime Intelligence Platform
Requires=docker.service
After=docker.service

[Service]
WorkingDirectory=/opt/maritime-intelligence-platform
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 8. Demo mode (no credentials)

For evaluation without external APIs:

```bash
docker compose -f docker-compose.demo.yml up --build
```

This builds a shared base image first, then starts all services in
`DEMO_MODE=true`. No `.env` credentials are required.

---

## 9. Updating

```bash
git pull
docker compose build
docker compose up -d
```

Database and volumes are preserved across updates. See `CHANGELOG.md` before
upgrading between minor versions.

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Service unhealthy at startup | Missing secrets → check `.env` (service logs show which variable is missing) |
| Detector reports model not loaded | `.onnx` file missing from `shared/models/` → rebuild the image |
| `data-ingestor` fails to download | Invalid CDSE credentials or AOI outside Sentinel-1 coverage |
| Dashboard can't reach a service | Services must be on the same network — do not override `*_URL` with `localhost` |
| Out of disk space | Sentinel-1 scenes are ~2 GB each; prune old scenes/volumes |
| `docker compose` v1 errors | Upgrade to the compose plugin (`docker compose version`) |

### Useful commands

```bash
docker compose ps                    # status + health
docker compose logs -f detector      # logs of one service
docker system df                     # disk usage of images/volumes
docker system prune -af              # clean unused images (careful!)
```

---

## 11. Reference

- Architecture & usage: [`README.md`](../README.md)
- API details per service: [`README.md`](../README.md#services)
- Security policy: [`SECURITY.md`](../SECURITY.md)
- Changelog: [`CHANGELOG.md`](../CHANGELOG.md)
