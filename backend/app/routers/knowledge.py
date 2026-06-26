from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from ..auth import get_current_user
from ..database import get_db
from ..schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    KnowledgeDocumentResponse,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
    KnowledgeRetrievalResult,
    DocumentChunkResponse,
)
from ..models import UserAccount
from ..knowledge_service import (
    create_knowledge_base,
    get_knowledge_bases,
    get_knowledge_base,
    add_document,
    search_knowledge,
    get_documents,
    process_document_task,
)
from ..task_queue import queue_task

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _status_value(status) -> str:
    return getattr(status, "value", status)


@router.post("/bases", response_model=KnowledgeBaseResponse)
async def create_kb(
    data: KnowledgeBaseCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base."""
    kb = await create_knowledge_base(
        db,
        current_user.enterprise_id,
        data.name,
        data.description,
        data.is_public,
    )
    return KnowledgeBaseResponse(
        id=kb.id,
        enterprise_id=kb.enterprise_id,
        name=kb.name,
        description=kb.description,
        is_public=kb.is_public,
        document_count=0,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.get("/bases", response_model=List[KnowledgeBaseResponse])
async def list_kbs(
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all knowledge bases."""
    kbs = await get_knowledge_bases(db, current_user.enterprise_id)
    return [
        KnowledgeBaseResponse(
            id=kb.id,
            enterprise_id=kb.enterprise_id,
            name=kb.name,
            description=kb.description,
            is_public=kb.is_public,
            document_count=len(kb.documents) if hasattr(kb, "documents") else 0,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
        for kb in kbs
    ]


@router.get("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_kb(
    kb_id: str,
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a knowledge base by ID."""
    kb = await get_knowledge_base(db, kb_id, current_user.enterprise_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return KnowledgeBaseResponse(
        id=kb.id,
        enterprise_id=kb.enterprise_id,
        name=kb.name,
        description=kb.description,
        is_public=kb.is_public,
        document_count=len(kb.documents) if hasattr(kb, "documents") else 0,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.post("/bases/{kb_id}/documents", response_model=KnowledgeDocumentResponse)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document to a knowledge base."""
    file_content = await file.read()
    
    try:
        doc = await add_document(
            db,
            kb_id,
            file.filename or "unknown",
            file_content,
            current_user.enterprise_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    
    # Queue document processing
    await queue_task(
        current_user.enterprise_id,
        "process_document",
        {"document_id": doc.id},
    )
    
    return KnowledgeDocumentResponse(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=_status_value(doc.status),
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/bases/{kb_id}/documents", response_model=List[KnowledgeDocumentResponse])
async def list_documents(
    kb_id: str,
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List documents in a knowledge base."""
    try:
        docs = await get_documents(db, kb_id, current_user.enterprise_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return [
        KnowledgeDocumentResponse(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=_status_value(doc.status),
            error_message=doc.error_message,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc in docs
    ]


@router.post("/search", response_model=KnowledgeRetrievalResponse)
async def search(
    data: KnowledgeRetrievalRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search knowledge base."""
    results = await search_knowledge(
        db,
        current_user.enterprise_id,
        data.query,
        data.knowledge_base_ids,
        data.top_k,
    )
    
    formatted_results = []
    for result in results:
        chunk = result["chunk"]
        doc = result["document"]
        formatted_results.append(
            KnowledgeRetrievalResult(
                chunk=DocumentChunkResponse(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    created_at=chunk.created_at,
                ),
                document=KnowledgeDocumentResponse(
                    id=doc.id,
                    knowledge_base_id=doc.knowledge_base_id,
                    filename=doc.filename,
                    file_type=doc.file_type,
                    file_size=doc.file_size,
                    status=_status_value(doc.status),
                    error_message=doc.error_message,
                    created_at=doc.created_at,
                    updated_at=doc.updated_at,
                ),
                score=result["score"],
            )
        )
    
    return KnowledgeRetrievalResponse(
        query=data.query,
        results=formatted_results,
    )
