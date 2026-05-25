"""
Imposer API — FastAPI Service
=============================

Endpoints:
- GET  /              — landing page
- GET  /health        — health check (used by Render to verify deploy)
- POST /detect        — main rotation detection endpoint
- GET  /docs          — auto-generated API docs (FastAPI feature)

Designed for Render/Railway free-tier deployment.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import time
import os

from algorithm import detect_rotation

# ============================================================
# APP SETUP
# ============================================================
app = FastAPI(
    title="Imposer API",
    description="Shape-matching rotation detection for prepress imposition",
    version="0.1.0",
)

# CORS — allow CEP plugin (origin file://, https://localhost, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open for now; tighten later when we add API keys
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================
class Point(BaseModel):
    x: float
    y: float


class DetectRequest(BaseModel):
    reference_points: List[List[float]] = Field(
        ...,
        description="Reference die points (artwork at canonical 0°): [[x,y], [x,y], ...]",
        min_length=3,
    )
    sheet_points: List[List[float]] = Field(
        ...,
        description="Sheet die points (same die rotated on sheet): [[x,y], [x,y], ...]",
        min_length=3,
    )
    fine: bool = Field(
        False,
        description="If true, test every 1°. If false, test only 0/90/180/-90 (faster).",
    )


class DetectResponse(BaseModel):
    angle: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    margin: float
    second_best: Optional[int] = None
    aspect_ratio_used: bool = False
    elapsed_ms: int
    error: Optional[str] = None


class BatchDetectRequest(BaseModel):
    reference_points: List[List[float]] = Field(..., min_length=3)
    sheet_dies: List[List[List[float]]] = Field(
        ...,
        description="Multiple sheet dies, each as point list",
    )
    fine: bool = False


class BatchDetectResponse(BaseModel):
    results: List[DetectResponse]
    total_dies: int
    elapsed_ms: int


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "service": "Imposer API",
        "version": "0.1.0",
        "endpoints": {
            "POST /detect": "Detect rotation between reference die and one sheet die",
            "POST /detect-batch": "Detect rotations for multiple sheet dies in one request",
            "GET /health": "Health check",
            "GET /docs": "Interactive API documentation",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "imposer-api"}


@app.post("/detect", response_model=DetectResponse)
def detect(request: DetectRequest):
    """Detect rotation of sheet die relative to reference die."""
    start = time.perf_counter()
    try:
        result = detect_rotation(
            request.reference_points,
            request.sheet_points,
            fine=request.fine,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return DetectResponse(
            angle=int(result['angle']),
            confidence=float(result['confidence']),
            margin=float(result['margin']),
            second_best=result.get('second_best'),
            aspect_ratio_used=result.get('aspect_ratio_used', False),
            elapsed_ms=elapsed_ms,
            error=result.get('error'),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Detection failed: {str(e)}")


@app.post("/detect-batch", response_model=BatchDetectResponse)
def detect_batch(request: BatchDetectRequest):
    """Detect rotations for multiple sheet dies against one reference. Faster than calling /detect N times."""
    start = time.perf_counter()
    results = []
    for sheet in request.sheet_dies:
        die_start = time.perf_counter()
        try:
            r = detect_rotation(request.reference_points, sheet, fine=request.fine)
            results.append(DetectResponse(
                angle=int(r['angle']),
                confidence=float(r['confidence']),
                margin=float(r['margin']),
                second_best=r.get('second_best'),
                aspect_ratio_used=r.get('aspect_ratio_used', False),
                elapsed_ms=int((time.perf_counter() - die_start) * 1000),
                error=r.get('error'),
            ))
        except Exception as e:
            results.append(DetectResponse(
                angle=0,
                confidence=0.0,
                margin=0.0,
                elapsed_ms=int((time.perf_counter() - die_start) * 1000),
                error=str(e),
            ))

    return BatchDetectResponse(
        results=results,
        total_dies=len(request.sheet_dies),
        elapsed_ms=int((time.perf_counter() - start) * 1000),
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
