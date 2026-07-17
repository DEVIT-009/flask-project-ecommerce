from flask import render_template
from . import admin_routes

@admin_routes.get("/dashboard")
def dashboard():
    return render_template("admin/layouts/dashboard.html")