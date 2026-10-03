from flask import Blueprint

api_routes = Blueprint(
    "api_routes",
    __name__
)

from api.controllers import product_controller, category_controller