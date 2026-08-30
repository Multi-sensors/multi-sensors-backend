from fastapi import FastAPI

app = FastAPI()

@app.get('/')
async def index():
    return {"hello": "world"}

@app.get('/about')
async def about():
    return "Multi sensor research project backend"

@app.get('/health')
async def health():
    return {"status": "ok"}