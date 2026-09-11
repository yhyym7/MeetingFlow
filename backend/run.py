import uvicorn

from app.config import get_settings


if __name__ == "__main__":
    settings = get_settings()
    # One process also remains the documented limit for the future job worker.
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)

