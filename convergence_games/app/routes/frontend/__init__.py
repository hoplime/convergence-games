from fastapi import APIRouter

from .experiments import router as experiments_router

router = APIRouter(include_in_schema=True)
router.include_router(experiments_router)
