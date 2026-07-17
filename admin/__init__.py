from flask import Blueprint

admin_routes = Blueprint(
    "admin_routes",
    __name__
)

from . import route