from flask import Flask
from api.controllers.product_controller import product_controller
from api.controllers.category_controller import category_controller
from web.routes.route import web_routes

app = Flask(
    __name__,
    template_folder='web/templates',
    static_folder='web/static'
)

# Register API blueprint
app.register_blueprint(product_controller)
app.register_blueprint(category_controller)
app.register_blueprint(web_routes)


if __name__ == '__main__':
    app.run(debug=True)

