"""FastAPI surface for the JML Compliance Audit Dashboard.

Routes:
  GET  /healthz          health probe
  GET  /joiners          full joiners analysis
  GET  /movers           movers (manager/dept/title changes)
  GET  /leavers          leavers + deprovisioning status
  GET  /privileged       standing privileges + role change history
  GET  /guests           guest account audit
  GET  /overview         executive overview (composite score + top actions)
  POST /agent            natural-language query
"""
import os
import time
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.joiners import run_joiners_analysis
from app.movers import run_movers_analysis
from app.leavers import run_leavers_analysis
from app.audit import run_privileged_audit
from app.guests import run_guests_audit
from app.overview import build_overview
from app.agent import run_agent

app = FastAPI(title="JML Compliance Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

CACHE_TTL_SECONDS = 30 * 60
_cache: dict = {}
_cache_locks_master = threading.Lock()
_cache_locks: dict = {}


def _key_lock(key: str) -> threading.Lock:
    """Return a per-key lock, creating one on demand."""
    with _cache_locks_master:
        lock = _cache_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _cache_locks[key] = lock
        return lock


def cached(key, fn, force=False):
    """Double-checked locking cache. Concurrent callers for the same key wait
    for one fill instead of all hitting Graph in parallel."""
    now = time.time()
    if not force and key in _cache:
        ts, val = _cache[key]
        if now - ts < CACHE_TTL_SECONDS:
            return val
    with _key_lock(key):
        # Re-check after acquiring the lock — another thread may have filled
        # the cache while we were waiting.
        now = time.time()
        if not force and key in _cache:
            ts, val = _cache[key]
            if now - ts < CACHE_TTL_SECONDS:
                return val
        val = fn()
        _cache[key] = (time.time(), val)
        return val


@app.get("/healthz")
def healthz():
    return {"service": "JML Compliance Audit API", "status": "running"}


@app.get("/joiners")
def joiners(refresh: bool = False):
    return cached("joiners", run_joiners_analysis, force=refresh)


@app.get("/movers")
def movers(refresh: bool = False):
    return cached("movers", run_movers_analysis, force=refresh)


@app.get("/leavers")
def leavers(refresh: bool = False):
    return cached("leavers", run_leavers_analysis, force=refresh)


@app.get("/privileged")
def privileged(refresh: bool = False):
    return cached("privileged", run_privileged_audit, force=refresh)


@app.get("/guests")
def guests(refresh: bool = False):
    return cached("guests", run_guests_audit, force=refresh)


@app.get("/overview")
def overview(refresh: bool = False):
    return build_overview(
        cached("joiners", run_joiners_analysis, force=refresh),
        cached("movers", run_movers_analysis, force=refresh),
        cached("leavers", run_leavers_analysis, force=refresh),
        cached("privileged", run_privileged_audit, force=refresh),
        cached("guests", run_guests_audit, force=refresh),
    )


class QueryRequest(BaseModel):
    query: str


@app.post("/agent")
def agent_endpoint(req: QueryRequest):
    return run_agent(
        req.query,
        joiners=cached("joiners", run_joiners_analysis),
        movers=cached("movers", run_movers_analysis),
        leavers=cached("leavers", run_leavers_analysis),
        audit=cached("privileged", run_privileged_audit),
        guests=cached("guests", run_guests_audit),
    )


# Serve built frontend if present (single-image deploy)
try:
    from fastapi.staticfiles import StaticFiles
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
except Exception:
    pass
