from remitx_api.controllers.health_controller import HealthController
from remitx_api.models.schemas.health import HealthRead
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_public_router

router = create_public_router(tags=[Tag.SYSTEM])
health_controller = HealthController()


@router.get("/health", response_model=HealthRead, summary="Check the API is up")
def health():
    """Answers without a session or a database round trip."""
    return health_controller.get_status()
