from remitx_api.controllers.health_controller import HealthController
from remitx_api.routes.routers import create_public_router

router = create_public_router()
health_controller = HealthController()


@router.get("/health")
def health():
    return health_controller.get_status()
