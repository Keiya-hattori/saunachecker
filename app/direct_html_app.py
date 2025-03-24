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
import asyncio

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

# 絶対パスを計算
# Render環境ではプロジェクトルートが/opt/render/project/src/
if IS_RENDER:
    BASE_DIR = Path('/opt/render/project/src')
else:
    BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 静的ファイルの設定
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# テンプレートの設定
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# スクレイパーのインスタンスを作成
scraper = SaunaScraper()

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """ホームページを表示"""
    # データベースからランキング情報を取得
    try:
        # JSONランキングを生成
        ranking_data = await generate_json_ranking(limit=40)
        review_count = await get_json_review_count()
    except Exception as e:
        print(f"ランキングデータ生成中にエラー発生: {str(e)}")
        print(traceback.format_exc())
        ranking_data = []
        review_count = 0
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "ranking_data": ranking_data, 
            "review_count": review_count,
            "is_scraping_running": False
        }
    )

@app.post("/analyze")
async def analyze(url: str = Form(...)):
    """既存のサウナの穴場評価APIエンドポイント"""
    try:
        result = await scraper.analyze_sauna(url)
        return result
    except Exception as e:
        return {"error": f"エラーが発生しました: {str(e)}"}

@app.get("/api/hidden_gem_reviews")
async def get_hidden_gem_reviews():
    """最新の穴場レビューを取得するエンドポイント"""
    try:
        reviews = await scraper.get_hidden_gem_reviews_test()
        return {"hidden_gem_reviews": reviews[:5]}  # 最新5件のみ返す
    except Exception as e:
        return {"error": str(e), "hidden_gem_reviews": []}

@app.post("/start_scraping")
async def start_scraping(background_tasks: BackgroundTasks):
    """スクレイピングを開始するエンドポイント"""
    try:
        # バックグラウンドタスクとしてスクレイピングを開始
        background_tasks.add_task(periodic_scraping)
        return {"status": "success", "message": "スクレイピングを開始しました"}
    except Exception as e:
        return {"status": "error", "message": f"エラーが発生しました: {str(e)}"}

@app.post("/toggle_auto_scraping")
async def toggle_auto_scrape():
    """自動スクレイピングの有効/無効を切り替えるエンドポイント"""
    try:
        result = toggle_auto_scraping()
        return result
    except Exception as e:
        return {"status": "error", "message": f"自動スクレイピング設定の変更中にエラーが発生しました: {str(e)}"}

@app.get("/debug", response_class=JSONResponse)
async def debug_info():
    """デバッグ用の情報を表示"""
    templates_dir = str(BASE_DIR / "templates")
    static_dir = str(BASE_DIR / "static")
    
    template_files = []
    if os.path.exists(templates_dir):
        template_files = os.listdir(templates_dir)
    
    static_files = []
    if os.path.exists(static_dir):
        static_files = os.listdir(static_dir)
    
    current_dir = os.getcwd()
    
    return {
        "base_dir": str(BASE_DIR),
        "templates_dir": templates_dir,
        "static_dir": static_dir,
        "template_files": template_files,
        "static_files": static_files,
        "current_dir": current_dir,
        "environment": "production" if IS_PRODUCTION else "development",
        "is_render": IS_RENDER
    }

@app.get("/home", response_class=HTMLResponse)
async def home():
    """静的HTMLでホームページを表示"""
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>サウナ穴場チェッカー</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        <style>
            body {
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                font-family: sans-serif;
            }
        </style>
    </head>
    <body class="bg-gray-100">
        <div class="container mx-auto px-4 py-8">
            <header class="text-center mb-12">
                <h1 class="text-4xl font-bold text-gray-800 mb-4">サウナ穴場チェッカー</h1>
                <p class="text-gray-600">サウナイキタイのレビューから穴場度を分析します</p>
                <div class="mt-4">
                    <a href="/debug" class="text-blue-500 hover:text-blue-700 underline">デバッグ情報を見る</a>
                    <span class="mx-2">|</span>
                    <a href="/json_ranking" class="text-blue-500 hover:text-blue-700 underline">穴場サウナランキングを見る →</a>
                </div>
            </header>

            <div class="bg-white rounded-lg shadow-md p-6 mb-8">
                <p>アプリケーションが正常に起動しました。</p>
            </div>
        </div>
    </body>
    </html>
    """

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
            
            # スクレイピングディレクトリも作成
            scraping_dir = data_dir / 'scraping'
            if not scraping_dir.exists():
                scraping_dir.mkdir(exist_ok=True)
                print(f"スクレイピングディレクトリを作成しました: {scraping_dir}")
            else:
                print(f"スクレイピングディレクトリを確認しました: {scraping_dir}")
                
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
            
        # スクレイピングディレクトリも作成
        scraping_dir = data_dir / 'scraping'
        if not scraping_dir.exists():
            scraping_dir.mkdir(exist_ok=True)
            print(f"開発環境でスクレイピングディレクトリを作成しました: {scraping_dir}")
    
    # データベース接続を確認
    db_path = os.path.join(data_dir, "sauna_temp.db")
    print(f"Using database at: {db_path}")
    
    # データベースの初期化
    try:
        db_initialized = await init_db()
        if db_initialized:
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
            
            # レビューが少ない場合、初期スクレイピングを実行
            if count[0] < 10:
                print("レビュー数が少ないため、初期スクレイピングを実行します...")
                try:
                    # バックグラウンドで非同期実行
                    asyncio.create_task(periodic_scraping())
                    print("初期スクレイピングタスクが開始されました")
                except Exception as e:
                    print(f"初期スクレイピングの開始中にエラー: {str(e)}")
                    print(traceback.format_exc())
            
        except Exception as e:
            print(f"Reviews table may not exist yet: {str(e)}")
            # テーブルがまだない場合も初期スクレイピングを実行
            try:
                print("テーブルがまだないため、初期スクレイピングを実行します...")
                asyncio.create_task(periodic_scraping())
                print("初期スクレイピングタスクが開始されました")
            except Exception as e:
                print(f"初期スクレイピングの開始中にエラー: {str(e)}")
                print(traceback.format_exc())
        
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

@app.get("/json_ranking", response_class=HTMLResponse)
async def json_ranking(request: Request):
    """サウナランキングを表示"""
    try:
        # JSONランキングを生成
        ranking_data = await generate_json_ranking(limit=40)
        review_count = await get_json_review_count()
        
        return templates.TemplateResponse(
            "ranking.html",
            {
                "request": request,
                "ranking_data": ranking_data,
                "review_count": review_count
            }
        )
    except Exception as e:
        print(f"ランキング生成中にエラー発生: {str(e)}")
        print(traceback.format_exc())
        return f"""
        <html>
            <head><title>エラー</title></head>
            <body>
                <h1>ランキングの取得中にエラーが発生しました</h1>
                <p>{str(e)}</p>
                <p><a href="/">ホームに戻る</a></p>
            </body>
        </html>
        """

if __name__ == "__main__":
    uvicorn.run("app.direct_html_app:app", host="0.0.0.0", port=8000, reload=True) 