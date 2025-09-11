# Hybrid Search – Development Guide

This repository includes a FastAPI application with PostgreSQL + pgvector integration for hybrid search (keyword + vector embeddings).  
Below are instructions for development, debugging, and container management.

---

## TL;DR

### First run

0. Dowload data

    1. Create a `data` folder in the root directory
    2. Download `articles.csv` in the `data` folder from the following link.
          ```text
          https://y7k3t6xm33.ufs.sh/f/mJpxIi6iJ8L6zCHT4QiNkoHlxjC0NJmERpfI15znaVL6y7dB
          ```
1. Build images
    ```bash
    docker compose build
    ```
2. Start the database (waits for healthcheck)
    ```bash
    docker compose up db
    ```
3. Backfill embeddings (one-off job)
    ```bash
    docker compose --profile jobs up backfill
    ```
4. Start the API
    ```bash
    docker compose up api
    ```
5. Open Swagger (OAS)
    ```bash
    http://localhost:8000/docs#/default/search_search_post
    ```

### Subsequent runs

```bash
docker compose up -d db
docker compose up -d api
```

---

## Debugging with Debugpy

To run the API in debug mode:

```bash
poetry run python -m debugpy --listen 5678 --wait-for-client   -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then attach to **debugpy** from your IDE.

---

## Docker Commands

### Lifecycle

- **Soft shutdown** (stop containers but keep volumes/networks):
  ```bash
  docker compose down
  ```

- **Hard shutdown** (remove containers + volumes):
  ```bash
  docker compose down -v
  ```

- **Start all services**:
  ```bash
  docker compose up
  ```

- **Start only the database**:
  ```bash
  docker compose up db
  ```

- **Start only the API**:
  ```bash
  docker compose up api
  ```

- **Run with backfill job**:
  ```bash
  docker compose --profile jobs up backfill
  ```

### Building

- **Rebuild after modifying Dockerfile**:
  ```bash
  docker compose build --no-cache backfill
  ```
  > Replace `backfill` with `api`, `db`, etc.

### Detached Mode

- **Start container in detached mode**:
  ```bash
  docker compose up -d db
  ```

- **View logs for detached containers**:
  ```bash
  docker compose logs -f db
  ```

---

## Poetry

- **Install dev dependencies** (example: faker):
  ```bash
  poetry add --group dev faker
  ```

---

## Troubleshooting

### Networking Errors

If you encounter:

```bash
Error response from daemon: failed to set up container networking: network <id> not found
```

Run the following in sequence:

```bash
# Stop and remove containers, networks, and orphans for this project
docker compose down --remove-orphans

# Remove dangling networks (safe)
docker network prune -f

# (Optional) Restart Docker Desktop/daemon if it’s been running a while
```

---

## Notes

- Run **db** first if seeding data.  
- Ensure backfill jobs are executed at least once after initialization.  
- Use `docker compose up api` during active development and attach to `debugpy` for live debugging.

---
