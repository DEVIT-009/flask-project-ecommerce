from flask import Blueprint, jsonify
import json
import os

category_controller = Blueprint('category_controller', __name__)

file_path = os.path.join(os.path.dirname(__file__), '../../sample/categories.json')

@category_controller.route('/api/categories', methods=['GET'])
def get_categories():
    with open(file_path, 'r') as f:
        categories = json.load(f)
    return jsonify(categories)