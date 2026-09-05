from fastapi import Depends, FastAPI

from auth import get_current_user

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

@app.get('/api/v1/me')
async def read_me(user: dict = Depends(get_current_user)):
    return {"user_id": user["sub"], "email": user["email"]}