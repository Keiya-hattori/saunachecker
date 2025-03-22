from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
from pathlib import Path
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re

app = FastAPI(title="サウナ穴場チェッカー・シンプル版")

# テンプレートとスタティックファイルの設定
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ディレクトリの作成
Path("templates").mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)
Path("test_files").mkdir(exist_ok=True)

# テスト用HTMLファイルのパス
TEST_HTML_PATHS = [
    Path("test_files") / "sauna_reviews_page1.html",
    Path("test_files") / "sauna_reviews_page2.html",
    Path("test_files") / "sauna_reviews_page3.html"
]

# 穴場キーワードとその重み付け
HIDDEN_GEM_KEYWORDS = {
    '穴場': 2,
    '隠れ家': 2,
    '静か': 1,
    '混んでいない': 1,
    '並ばない': 1,
    'ゆったり': 1,
    '落ち着く': 1,
    '知る人ぞ知る': 2,
    '教えたくない': 2,
    '空いている': 1,
    'のんびり': 1,
    '穴場スポット': 2,
}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    print("ホームページにアクセスがありました")
    print(f"テンプレートディレクトリ: {templates.directory}")
    print(f"index.htmlへのパス: {Path(templates.directory) / 'index.html'}")
    print(f"index.htmlが存在するか: {(Path(templates.directory) / 'index.html').exists()}")
    
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        print(f"テンプレート読み込みエラー: {str(e)}")
        return HTMLResponse(f"""
        <html>
            <head>
                <title>エラー</title>
            </head>
            <body>
                <h1>エラーが発生しました</h1>
                <p>{str(e)}</p>
                <p>テンプレートディレクトリ: {templates.directory}</p>
                <p>index.htmlの存在: {(Path(templates.directory) / 'index.html').exists()}</p>
            </body>
        </html>
        """)

@app.post("/analyze")
async def analyze(url: str = Form(...)):
    """URLからサウナ施設の穴場評価を行う"""
    print(f"分析リクエストを受信: {url}")
    try:
        # 分析結果を返す
        return {
            "name": "テスト用サウナ施設",
            "is_hidden_gem": True,
            "score": 4.2,
            "max_score": 5.0,
            "reasons": [
                "「穴場」キーワードが見つかりました",
                "「静か」が3回言及されています"
            ],
            "review_count": 15
        }
    except Exception as e:
        print(f"分析エラー: {str(e)}")
        return {"error": f"エラーが発生しました: {str(e)}"}

@app.get("/api/hidden_gem_reviews")
async def get_hidden_gem_reviews():
    """テスト用の穴場レビューを取得"""
    print("穴場レビュー取得リクエストを受信")
    try:
        # テスト用のデータを返す
        return {
            "hidden_gem_reviews": [
                {
                    "name": "サウナA",
                    "url": "https://example.com/saunaA",
                    "review": "とても静かで穴場のサウナです。混雑していないので、ゆっくりと楽しめます。",
                    "keywords": ["穴場", "静か", "混んでいない"]
                },
                {
                    "name": "サウナB",
                    "url": "https://example.com/saunaB",
                    "review": "隠れ家的なサウナで、落ち着いた雰囲気が最高です。",
                    "keywords": ["隠れ家", "落ち着く"]
                },
                {
                    "name": "サウナC",
                    "url": "https://example.com/saunaC",
                    "review": "知る人ぞ知る穴場スポット。教えたくないほど良いサウナです。",
                    "keywords": ["知る人ぞ知る", "穴場スポット", "教えたくない"]
                }
            ]
        }
    except Exception as e:
        print(f"レビュー取得エラー: {str(e)}")
        return {"error": str(e), "hidden_gem_reviews": []}

@app.get("/minimal", response_class=HTMLResponse)
async def minimal_test(request: Request):
    """最小限のテストページ"""
    print("最小限テストページにアクセスがありました")
    try:
        return templates.TemplateResponse("minimal.html", {"request": request})
    except Exception as e:
        print(f"テンプレート読み込みエラー: {str(e)}")
        return HTMLResponse(f"<h1>エラー</h1><p>{str(e)}</p>")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True) 