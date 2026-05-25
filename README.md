# Imposer API

Shape-matching rotation detection service for prepress imposition.

Built with FastAPI + Shapely. Validated on real production packaging files (Pakistani box dies: Colgate, Sooper, Qourma).

## Endpoints

- `GET /health` — health check
- `POST /detect` — detect rotation between reference and sheet die
- `POST /detect-batch` — batch version for multiple sheet dies
- `GET /docs` — interactive API documentation

## Local Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then visit `http://localhost:8000/docs`.

## Deploy

See `DEPLOY.md` for step-by-step Render deployment instructions.
