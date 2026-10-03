from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

db = SQLAlchemy()
migrate = Migrate()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    strategy="moving-window",
)

csrf = CSRFProtect()
cors = CORS(resources={
    r"/api/v1/*": {
        "origin": [
            "http://localhost:3000",
            "http://localhost:4000",
        ]
    }
})