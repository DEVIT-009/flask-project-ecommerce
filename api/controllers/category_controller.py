from api import api_routes
from flask import jsonify
import json
import os

file_path = os.path.join(os.path.dirname(__file__), '../../sample/categories.json')

@api_routes.route('/api/categories', methods=['GET'])
def get_categories():
    with open(file_path, 'r') as f:
        categories = json.load(f)
    return jsonify(categories)