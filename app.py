from flask import Flask

from extensions import db, migrate

from api.controllers.product_controller import product_controller
from api.controllers.category_controller import category_controller
from admin import admin_routes
from web import web_routes

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///mydb.sqlite3"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate.init_app(app, db)

# import models AFTER db init
import api.models

# Register blueprint
app.register_blueprint(product_controller)
app.register_blueprint(category_controller)

app.register_blueprint(web_routes)
app.register_blueprint(admin_routes)


if __name__ == "__main__":
    app.run(debug=True)