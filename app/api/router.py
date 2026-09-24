from fastapi import APIRouter
from app.api.v1 import auth, oauth, users, roles

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(oauth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
