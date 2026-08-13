import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from src.api.auth import verify_api_key
from src.rag.doc_retriever import ingest_document

router = APIRouter(prefix="/api/v1/documents", tags=["documents"], dependencies=[Depends(verify_api_key)])

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    file_path = f"data/uploads/{file.filename}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
        
    try:
        chunks_added = ingest_document(file_path)
        return {"filename": file.filename, "status": "ingested", "chunks": chunks_added}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        pass
