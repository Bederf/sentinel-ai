# SENTINEL Release Installation

## Prerequisites

- Docker 24+ for container-based deployment
- A Linux host with a writable application directory
- Network access to the configured Supabase instance
- A valid `sentinel-v1.0.0.tar.gz` release bundle or equivalent deployment artifact

## Required Environment Variables

Set these before starting the backend:

- `SITE_ID`
- `PLANT_SITE_ID`
- `BUILDING_NAME`
- `JWT_SECRET_KEY`
- `SENTRY_WEBHOOK_SECRET`
- `CONSENT_HASH_SALT`
- `INGESTION_MODE`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

Optional variables:

- `HOST` - default `0.0.0.0`
- `PORT` - default `8000`
- `LOG_LEVEL` - default `info`
- `APP_NAME`
- `APP_VERSION`
- `ENVIRONMENT`
- `DEBUG`
- `REDIS_URL`
- `REDIS_ENABLED`
- `STORAGE_PROVIDER`

## Startup Commands

### Direct binary

```bash
cp .env.template .env
# edit .env with deployment values
set -a
. ./.env
set +a
./sentinel-backend
```

### Docker image

Build from the `deployment/` context:

```bash
docker build -f deployment/Dockerfile.release deployment -t sentinel-release:latest
```

Run the container with your environment file:

```bash
docker run --rm \
  --env-file deployment/.env \
  -p 8000:8000 \
  sentinel-release:latest
```

## Health Check

The backend health endpoint is:

```text
http://localhost:8000/api/health
```

Use it to confirm startup before promoting traffic.

## Upgrade Procedure

1. Download the new release bundle.
2. Back up the current `.env` and any local storage.
3. Replace the binary or rebuild the Docker image from the updated release assets.
4. Restart the service or container.
5. Verify `http://localhost:8000/api/health` returns `200`.
6. Confirm the API and frontend integrations still point at the intended site and Supabase environment.

## Notes

- The release image expects `dist/sentinel-backend` to exist in the Docker build context.
- `deployment/.env.template` is the source template for production `.env` files.
- Do not commit secrets into the repository.
