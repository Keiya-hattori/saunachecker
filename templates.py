from fastapi.templating import Jinja2Templates
import os

# テンプレートディレクトリの設定
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
TEMPLATES = Jinja2Templates(directory=TEMPLATES_DIR) 