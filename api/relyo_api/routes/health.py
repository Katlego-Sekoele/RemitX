from flask import Blueprint, jsonify

from relyo_api.controllers.health_controller import HealthController

health_bp = Blueprint("health", __name__)
health_controller = HealthController()


@health_bp.get("/health")
def health():
    return jsonify(health_controller.get_status())
