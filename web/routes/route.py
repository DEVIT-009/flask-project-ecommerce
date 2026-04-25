from flask import render_template, Blueprint, request

from web.services.category_service import CategoryService
from web.services.product_service import ProductService

web_routes = Blueprint('web_routes', __name__)

@web_routes.route('/')
def index():
    products = ProductService.get_all()
    return render_template("layouts/index.html", products=products[:6])

@web_routes.route('/products')
def product_list():
    products = ProductService.get_all()
    categories = CategoryService.get_all()
    selected_category_title = request.args.get('category_title', type=str)

    if selected_category_title:
        products = [
            product for product in products
            if product.get("category", {}).get("title", "").lower() == selected_category_title.lower()
        ]

    genre_list = ["fiction", "non-fiction", "technology", "business", "science"]
    author_list = ["J.K. Rowling", "George Orwell", "Stephen King"]
    format_list = ["paperback", "hardcover", "ebook"]

    return render_template(
        "layouts/product_layout.html",
        products=products,
        categories=categories,
        genre_list=genre_list,
        author_list=author_list,
        format_list=format_list,
        selected_category_title=selected_category_title,
    )

@web_routes.route('/product-detail')
def detail():
    product_id = request.args.get('id', type=int)
    category_id = request.args.get('category_id', type=int)

    product = ProductService.get_by_id(product_id)
    products = ProductService.get_by_category(category_id, product_id)

    return render_template(
        'layouts/product_detail.html',
        product=product,
        products=products
    )

@web_routes.route('/cart')
def cart():
    products = ProductService.get_all()
    return render_template("layouts/cart_layout.html", products=products)

@web_routes.route('/checkout')
def checkout():
    products = ProductService.get_all()
    return render_template("layouts/checkout_layout.html", products=products)

@web_routes.app_errorhandler(404)
def error_404(e):
    return render_template("error/error404.html")

@web_routes.app_errorhandler(500)
def error_500(e):
    return render_template("error/error500.html")
