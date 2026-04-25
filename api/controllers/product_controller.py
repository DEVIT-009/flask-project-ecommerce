from flask import Blueprint, jsonify
import json
import os

product_controller = Blueprint('product_controller', __name__)

file_path = os.path.join(os.path.dirname(__file__), '../../sample/products.json')

@product_controller.route('/api/products', methods=['GET'])
def get_products():
    with open(file_path, 'r') as f:
        products = json.load(f)
    return jsonify(products)