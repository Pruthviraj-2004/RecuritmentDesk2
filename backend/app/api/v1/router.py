from fastapi import APIRouter

from app.api.v1.endpoints import accounts, auth, candidates, duplicates, exports, internal, ops, requirements

api_router = APIRouter(prefix="/api/v1")
for r in (auth.router, accounts.router, requirements.router, candidates.router, duplicates.router, exports.router, internal.router, ops.router, ops.health_router):
    api_router.include_router(r)
