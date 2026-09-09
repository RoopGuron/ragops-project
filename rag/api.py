import os
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from rag.answer import answer_question

app = FastAPI(title="RAG Query API")

_CONFIG_PATH = os.getenv("RAG_CONFIG_PATH", "rag/champion_config.json")


# Define the structure of the POST body
class QueryRequest(BaseModel):
    query: str


@app.post("/query")
async def post_query(request: QueryRequest):
    # Process your query here
    return {"received_query": request.query}

# uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

