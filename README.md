# Hello

To `Run in Debug` run the following command:
```bash
poetry run python -m debugpy --listen 5678 --wait-for-client \
  -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
and then attach to debugpy.