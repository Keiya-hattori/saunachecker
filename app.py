from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import uvicorn
from templates import TEMPLATES
from app.services.scraper import SaunaScraper
from app.models.database import init_db, get_sauna_ranking

# アプリケーションの初期化
app = FastAPI(title="サウナ穴場チェッカー")

# 静的ファイルの設定
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# テストファイルディレクトリの設定
TEST_FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_files")

# スクレイパーインスタンスの作成
scraper = SaunaScraper()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """ホームページを表示します"""
    return TEMPLATES.TemplateResponse("index.html", {"request": request})

@app.get("/api/ranking")
async def get_ranking():
    """サウナのランキングを取得します"""
    try:
        rankings = get_sauna_ranking()
        return {
            "status": "success",
            "message": f"{len(rankings)}件のランキングデータを取得しました",
            "ranking": rankings
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"ランキングの取得に失敗しました: {str(e)}"
        }

@app.post("/api/analyze", response_class=JSONResponse)
async def analyze_sauna(sauna_url: str = Form(...)):
    """指定されたサウナURLを分析します"""
    try:
        if not sauna_url or not sauna_url.strip():
            return {"status": "error", "message": "サウナURLを入力してください"}
        
        result = await scraper.analyze_sauna(sauna_url)
        return result
    except Exception as e:
        return {
            "status": "error",
            "message": f"エラーが発生しました: {str(e)}"
        }

@app.get("/api/test/scraping")
async def test_scraping():
    """スクレイピングテストを実行します"""
    try:
        reviews = await scraper.get_hidden_gem_reviews_test()
        
        # サウナ名ごとに集計
        sauna_counts = {}
        for review in reviews:
            sauna_name = review["sauna_name"]
            keywords = review["keywords"]
            
            if sauna_name not in sauna_counts:
                sauna_counts[sauna_name] = {"count": 0, "keywords": set()}
            
            sauna_counts[sauna_name]["count"] += 1
            for keyword in keywords:
                sauna_counts[sauna_name]["keywords"].add(keyword)
        
        # ランキング作成
        ranking = []
        for sauna_name, data in sauna_counts.items():
            ranking.append({
                "sauna_name": sauna_name,
                "count": data["count"],
                "keywords": list(data["keywords"])
            })
        
        # カウント数でソート
        ranking.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "status": "success",
            "message": f"{len(reviews)}件のテストレビューを取得しました",
            "ranking": ranking
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"スクレイピングテストに失敗しました: {str(e)}"
        }

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時に実行される処理"""
    await init_db()
    print("データベースを初期化しました")

if __name__ == "__main__":
    # 環境変数からポートを取得するか、デフォルト値を使用
    port = int(os.environ.get("PORT", 9000))
    
    # 本番環境かどうかを確認
    is_production = os.environ.get("ENVIRONMENT") == "production"
    
    # Uvicornサーバーを起動
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=not is_production
    ) 