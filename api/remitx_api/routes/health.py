from fastapi import APIRouter

from remitx_api.controllers.health_controller import HealthController

router = APIRouter()
health_controller = HealthController()


@router.get("/health")
def health():
    return health_controller.get_status()
