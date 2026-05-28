from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..models import UserAccount
from ..services import BUILTIN_TOOLS

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(current_user: UserAccount = Depends(get_current_user)):
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
