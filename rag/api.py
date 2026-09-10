import asyncio
import os
import json
from pathlib import Path
from fastapi import FastAPI, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from rag.config import load_config
from contextlib import asynccontextmanager

from rag.answer import answer_question


# 1. Define your lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    # This runs BEFORE the server starts receiving requests
    print("Initializing expensive resources (e.g., Configuration Setup)...")
    await asyncio.sleep(1) # Simulating an async setup task
    
    # Store the RagConfig in the app state for later use
    app.state.rag_config = load_config()
    
    yield  # The application yields control here while running and serving requests
    
    # --- SHUTDOWN LOGIC ---
    # This runs AFTER the server stops receiving requests, right before exiting
    print("Cleaning up resources and closing connections...")
    app.state.rag_config = None
    print("Shutdown complete.")


app = FastAPI(title="RAG Query API", lifespan=lifespan)


# Define the structure of the POST body
class QueryPayload(BaseModel):
    query: str

# Define QueryResponse model for the response
class QueryResponse(BaseModel):
    received_query: str
    answer: str
    retrieved: list
    invented_citations: list
    citations: list


@app.post("/query", status_code=status.HTTP_200_OK)
async def post_query(query_payload: QueryPayload,
    request: Request):
    # Process your query here
    try:
        ans = await run_in_threadpool(
            answer_question,
            question=query_payload.query, 
            config=request.app.state.rag_config
        )
    except Exception as e:
        print(f"Error occurred while answering question: {e}")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": "Bad Gateway",
                "message": "Answering the question failed. Please check the server logs for more details.",
                "details": str(e)
            }
        )

    print(ans.text.strip() or "(empty answer)")
    print("-" * 72)
    print(f"retrieved: {ans.retrieval.get('retrieved', [])}")
    if ans.invented_citations:
        print(f"invented citations: {ans.invented_citations}")

    response_model = QueryResponse(
        received_query=query_payload.query,
        answer=ans.text.strip() or "(empty answer)",
        retrieved=ans.retrieval.get('retrieved', []),
        invented_citations=ans.invented_citations,
        citations=[ citation.__str__() for citation in ans.citations ]
    )
    return response_model


@app.get("/health", status_code=200)
async def health_check():
    # Here you can add checks for database connectivity, service availability, etc.
    # 2. Return 200 OK if everything is running smoothly
    return {
        "status": "healthy",
        "version": "1.0.0",
        "message": "RAG Query API is up and running!"
    }

# uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

