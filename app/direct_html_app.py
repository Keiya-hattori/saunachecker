from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import traceback
from datetime import datetime
from pathlib import Path
import uvicorn

from app.models.database import get_db, init_db
from app.database import save_reviews, update_ratings
from app.tasks import toggle_auto_scraping, periodic_scraping, reset_scraping_state, load_scraping_state
from app.services.scraper import SaunaScraper
from app.services.ranking import generate_sauna_ranking as generate_json_ranking, get_review_count as get_json_review_count

# 環境変数
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"
IS_RENDER = os.environ.get('RENDER', 'False') == 'True'

# FastAPIアプリケーションを作成
app = FastAPI()

# 静的ファイルの設定
app.mount("/static", StaticFiles(directory="static"), name="static")

# テンプレートの設定
templates = Jinja2Templates(directory="templates")

# スクレイパーのインスタンスを作成
scraper = SaunaScraper()

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化イベント"""
    
    # データディレクトリの設定
    if IS_RENDER:
        data_dir = Path('/opt/render/project/src/data')
        try:
            if not data_dir.exists():
                data_dir.mkdir(exist_ok=True)
                print(f"Render環境で永続データディレクトリを作成しました: {data_dir}")
            else:
                print(f"Render環境で永続データディレクトリを確認しました: {data_dir}")
                
            # データディレクトリ内のファイルを確認
            files = list(data_dir.glob('*'))
            print(f"データディレクトリ内のファイル: {[f.name for f in files]}")
        except Exception as e:
            print(f"Render環境での永続データディレクトリの初期化エラー: {e}")
            print(traceback.format_exc())
    else:
        # 開発環境での設定
        data_dir = Path('data')
        if not data_dir.exists():
            data_dir.mkdir(exist_ok=True)
            print(f"開発環境でデータディレクトリを作成しました: {data_dir}")
    
    # データベース接続を確認
    db_path = os.path.join(data_dir, "sauna_temp.db")
    print(f"Using database at: {db_path}")
    
    # データベースの初期化
    try:
        await init_db()
        print("データベースの初期化が完了しました")
        
        # 初期化ステータスを表示
        db = get_db()
        result = db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        table_count = result[0]
        print(f"Database initialized with {table_count} tables")
        
        # レビュー数を確認
        try:
            count = db.execute("SELECT COUNT(*) FROM reviews").fetchone()
            print(f"Found {count[0]} reviews in database")
        except Exception as e:
            print(f"Reviews table may not exist yet: {str(e)}")
        
    except Exception as e:
        print(f"Database initialization error: {str(e)}")
        print(traceback.format_exc())
    
    # スクレイピング状態を読み込む
    try:
        load_scraping_state()
        print("Scraping state loaded successfully")
    except Exception as e:
        print(f"Error loading scraping state: {str(e)}")
        print(traceback.format_exc())
    
    # 初期化完了ログ
    print("Application startup completed")

if __name__ == "__main__":
    uvicorn.run("app.direct_html_app:app", host="0.0.0.0", port=8000, reload=True) 