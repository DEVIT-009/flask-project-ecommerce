import requests

BASE_API_URL = "http://127.0.0.1:5000/api/categories"

class CategoryService:

    @staticmethod
    def get_all():
        response = requests.get(BASE_API_URL)
        if response.status_code in [200, 201]:
            categories_json = response.json()
            categories_dict = categories_json.get('data', [])
            return categories_dict
        return []
