from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import traceback
from datetime import datetime
from pathlib import Path

from database import get_db, save_reviews, update_ratings
from tasks import toggle_auto_scraping, periodic_scraping, reset_scraping_state
from scraper import SaunaScraper, transform_reviews

# FastAPIアプリケーションを作成
app = FastAPI()

# 静的ファイルの設定
app.mount("/static", StaticFiles(directory="static"), name="static")

# テンプレートの設定
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化イベント"""
    
    # 永続データディレクトリの設定
    data_dir = "/opt/render/project/src/data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        print(f"Created persistent data directory: {data_dir}")
    
    print(f"Data directory contents: {os.listdir(data_dir)}")
    
    # データベース接続を確認
    db_path = os.path.join(data_dir, "sauna_temp.db")
    print(f"Using database at: {db_path}")
    
    # 初期化ステータスを表示
    try:
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
    
    # 初期化完了ログ
    print("Application startup completed")
    
    # スクレイピング状態を読み込む（tasks.pyで定義されている関数を使用）
    try:
        from tasks import load_scraping_state
        load_scraping_state()
        print("Scraping state loaded successfully")
    except Exception as e:
        print(f"Error loading scraping state: {str(e)}")
        print(traceback.format_exc()) 