from fastapi import APIRouter

from ..services import BUILTIN_TOOLS

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools():
    return [
        {
            "name": t.name,
            "description": t.description,
            "category": getattr(t, "category", "general"),
            "requires_approval": t.requires_approval,
            "spec": t.get_spec().input_schema,
        }
        for t in BUILTIN_TOOLS
    ]
