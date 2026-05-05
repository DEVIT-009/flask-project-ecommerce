import requests

BASE_API_URL = "http://127.0.0.1:8000/api/products"

class ProductService:

    @staticmethod
    def get_all():
        response = requests.get(BASE_API_URL)
        if response.status_code in [200, 201]:
            products_json = response.json()
            products_dict = products_json.get('data', [])
            return products_dict
        return []

    @staticmethod
    def get_by_id(product_id: int):
        products = ProductService.get_all()

        for item in products:
            if item["id"] == product_id:
                return item

        return None

    @staticmethod
    def get_by_category(category_id: int, product_id: int):
        products = ProductService.get_all()

        related_products = [
            item for item in products
            if item["category"]["id"] == category_id and item["id"] != product_id
        ]

        return [] if not related_products else related_products