"""BuilderDNA 2.0 FastAPI application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.router.radar import router as radar_router

app = FastAPI(
    title="BuilderDNA API",
    description="Technology Evolution Intelligence Engine",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(radar_router)


def main():
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
