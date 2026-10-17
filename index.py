"""Explicit Vercel FastAPI entrypoint."""
import os

# Set limits before the application imports numpy/scipy/sklearn.
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(name, "1")

from app.main import app
