"""Read-only overview and shared navigation for the existing data workspaces."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from neo4j import Query

from app.bulk_import.api import manager
from app.modules.kg_import.config import Settings as KGSettings
from app.modules.rag.batch import now

WEB = Path(__file__).parent / "web"
RAG_JOBS = "/modules/rag/api/v1/rag/batch/jobs"
log = logging.getLogger("uvicorn.error")


async def internal_get(app, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://workspace.internal"
    ) as client:
        response = await client.get(path)
        response.raise_for_status()
        return response.json()


async def guarded(name, operation):
    try:
        return await asyncio.wait_for(operation(), timeout=8)
    except Exception:
        log.warning("data_workspace.read_failed module=%s", name, exc_info=True)
        return {
            "state": "unavailable",
            "message": "Chưa đọc được dữ liệu. Kiểm tra kết nối và log backend.",
        }


async def rag_summary(app):
    rag = app.state.embedded_apps["rag"]
    if not getattr(rag.state, "available", False):
        return {
            "state": "unavailable",
            "message": "Module RAG chưa khởi tạo thành công.",
        }
    batch = getattr(rag.state, "batch", None)
    if batch is not None and batch.active:
        return {
            "state": "busy",
            "message": "RAG đang nạp dữ liệu. Thống kê sẽ cập nhật sau khi hoàn tất.",
        }
    health = await internal_get(app, "/modules/rag/api/v1/rag/health")
    stats = await internal_get(app, "/modules/rag/api/v1/rag/stats")
    return {
        "state": "ready",
        "mode": health.get("mode"),
        "stats": {
            k: stats[k]
            for k in ("documents", "chunks", "propositions", "vectors", "needs_reindex")
            if k in stats
        },
        "chunking": stats.get("chunking", {}).get("method"),
        "message": "MongoDB và Qdrant"
        if health.get("mode") == "live"
        else "Demo: dữ liệu thử nghiệm cục bộ",
    }


async def kg_vector_summary():
    return {
        "state": "disabled",
        "message": "KG dùng hợp nhất tên/alias chính xác; không cần chỉ mục embedding.",
    }


def kg_graph_summary(app):
    explorer = app.state.embedded_apps["kg_explorer"]
    if not getattr(explorer.state, "available", False):
        return {
            "state": "unavailable",
            "message": "Module KG chưa khởi tạo thành công.",
        }
    service = explorer.state.get_query_service()
    graph_label = getattr(service, "global_label", "Entity")
    if not isinstance(graph_label, str):
        graph_label = "Entity"
    query = Query(
        """CALL () { MATCH (e:Entity) RETURN count(e) AS entities }
CALL () { MATCH (:Entity)-[r]->(:Entity) RETURN count(r) AS relations }
RETURN entities, relations""".replace(":Entity", ":" + graph_label),
        timeout=3,
    )
    with service.driver.session(
        database=service.database, default_access_mode="READ"
    ) as session:
        stats = dict(session.run(query).single())
    mongo = {"state": "unavailable", "message": "Chưa đọc được tài liệu MongoDB."}
    try:
        if service.evidence_store is not None:
            db = service.evidence_store.coll.database
            db.command("ping")
            from app.kg_global.query import active

            sid = active() if graph_label != "Entity" else None
            stats["documents"] = (
                db["global_documents"].count_documents(
                    {"snapshot": sid}, maxTimeMS=3000
                )
                if sid
                else db["documents"].count_documents({}, maxTimeMS=3000)
            )
            mongo = {"state": "ready", "message": "Kho tài liệu MongoDB sẵn sàng."}
    except Exception:
        log.warning("data_workspace.read_failed module=kg_mongodb", exc_info=True)
    return {
        "state": "ready",
        "message": "Neo4j của Knowledge Graph",
        "stats": stats,
        "mongodb": mongo,
    }


async def kg_summary(app):
    graph, vector = await asyncio.gather(
        guarded("kg_graph", lambda: asyncio.to_thread(kg_graph_summary, app)),
        guarded("kg_vector", kg_vector_summary),
    )
    return {**graph, "vector": vector}


async def context_summary(app):
    module = app.state.embedded_apps["context"]
    if not getattr(module.state, "available", False):
        return {
            "state": "unavailable",
            "message": "Module Context chưa khởi tạo thành công.",
        }
    container = module.state.container
    if container.driver is None:
        history = container.history_repository._turns
        patients = container.patient_repository._facts
        stats = {
            "patients": len(set(patients) | {p for p, _ in history}),
            "sessions": len(history),
            "turns": sum(len(turns) for turns in history.values()),
            "facts": sum(len(facts) for facts in patients.values()),
        }
    else:
        query = Query(
            """CALL () { MATCH (p:Patient) RETURN count(p) AS patients }
CALL () { MATCH (s:Session) RETURN count(s) AS sessions }
CALL () { MATCH (t:Turn) RETURN count(t) AS turns }
CALL () { MATCH (f:ClinicalStatement) RETURN count(f) AS facts }
RETURN patients, sessions, turns, facts""",
            timeout=3,
        )
        async with container.driver.session(
            database=container.settings.neo4j_database, default_access_mode="READ"
        ) as session:
            stats = dict(await (await session.run(query)).single())
    return {
        "state": "ready",
        "mode": container.settings.graph_backend,
        "stats": stats,
        "message": "Neo4j của Context & Patient"
        if container.driver is not None
        else "Bộ nhớ tạm: dữ liệu mất khi backend dừng.",
    }


def create_router(frontend_origins=()):
    router = APIRouter()

    @router.get("/data", include_in_schema=False)
    @router.get("/data/", include_in_schema=False)
    async def page():
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})

    @router.get("/data-assets/{filename}", include_in_schema=False)
    async def asset(
        filename: Literal[
            "app.js",
            "style.css",
            "embed.js",
            "embed.css",
            "logo.png",
            "pulmograph.svg",
            "fonts.css",
            "be-vietnam-pro-vietnamese-400-normal.woff2",
            "be-vietnam-pro-latin-ext-400-normal.woff2",
            "be-vietnam-pro-latin-400-normal.woff2",
            "be-vietnam-pro-vietnamese-600-normal.woff2",
            "be-vietnam-pro-latin-ext-600-normal.woff2",
            "be-vietnam-pro-latin-600-normal.woff2",
        ],
    ):
        return FileResponse(WEB / filename, headers={"Cache-Control": "no-cache"})

    @router.get("/api/v1/data/config")
    async def config():
        return {
            "frontend_origins": [origin for origin in frontend_origins if origin != "*"]
        }

    @router.get("/api/v1/data/overview")
    async def overview(request: Request):
        app = request.app
        if not getattr(app.state, "data_overview_lock", None):
            app.state.data_overview_lock = asyncio.Lock()
        async with app.state.data_overview_lock:
            cache = getattr(app.state, "data_overview_cache", None)
            if cache and time.monotonic() - cache[0] < 10:
                return cache[1]
            values = await asyncio.gather(
                guarded("rag", lambda: rag_summary(app)),
                guarded("kg", lambda: kg_summary(app)),
                guarded("context", lambda: context_summary(app)),
            )
            result = {
                "checked_at": now(),
                "modules": dict(zip(("rag", "kg", "context"), values)),
            }
            app.state.data_overview_cache = (time.monotonic(), result)
            return result

    @router.get("/api/v1/data/jobs")
    async def jobs(request: Request):
        async def module_jobs(module):
            if module == "rag":
                return await internal_get(request.app, RAG_JOBS + "?limit=30")
            return manager(request, module).list()

        modules = ("rag", "kg", "context")
        results = await asyncio.gather(
            *(guarded(module, lambda m=module: module_jobs(m)) for module in modules)
        )
        items, active, errors = [], {}, {}
        fields = (
            "job_id",
            "mode",
            "status",
            "started_at",
            "finished_at",
            "total",
            "processed",
            "completed",
            "skipped",
            "failed",
            "partial",
            "needs_review",
        )
        for module, result in zip(modules, results):
            if result.get("state") == "unavailable":
                errors[module] = result["message"]
                continue
            active[module] = result.get("active_job_id")
            for job in result.get("items", [])[:30]:
                items.append(
                    {
                        **{key: job[key] for key in fields if key in job},
                        "module": module,
                    }
                )
        items.sort(key=lambda job: job.get("started_at", ""), reverse=True)
        return {
            "items": items,
            "active": active,
            "errors": errors,
            "per_module_limit": 30,
        }

    return router
