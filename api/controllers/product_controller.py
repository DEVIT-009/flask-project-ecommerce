from static.mock.products import products  # <-- Add .products
from flask import jsonify
import json
import os
from api import api_routes

@api_routes.get('/products')
def product_list():
    return products