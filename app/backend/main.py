from fastapi import FastAPI

from .route import router

fastapi_app = FastAPI(title="Network Debugger Agent")
fastapi_app.include_router(router)