from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI()

@app.get("/api/index")
async def index_test():
    return PlainTextResponse("FastAPI index working!")

@app.get("/api/health")
async def health_test():
    return PlainTextResponse("FastAPI health working!")