from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.chore import lifespan
from app.services.crud_item_store import router as item_store_router
from app.shared.exceptions import AppException
from app.shared.responses import ErrorResponse


app = FastAPI(title="OpenTaberna API", lifespan=lifespan)


# Global exception handler for AppException
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Handle all AppException instances and convert them to HTTP responses.

    The ErrorResponse.from_exception method automatically maps error categories
    to appropriate HTTP status codes (404, 422, 401, 403, 400, 500, 502).
    """
    error_response = ErrorResponse.from_exception(exc)
    return JSONResponse(
        status_code=error_response.status_code,
        content=error_response.model_dump(mode="json"),
    )


origins = ["*"]  # Consider restricting this in a production environment

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include crud-item-store router
app.include_router(item_store_router, prefix="/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
