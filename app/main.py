from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
import uvicorn
from pathlib import Path
from app.services.scraper import SaunaScraper
import json
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="サウナ穴場チェッカー")

# テンプレートとスタティックファイルの設定
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# スクレイパーのインスタンスを作成
scraper = SaunaScraper()

@app.get("/", response_class=HTMLResponse)
async def home():
    """トップページ - 直接HTML版"""
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
            .score {
                font-size: 1.2em;
                font-weight: bold;
            }
            .hidden-gem {
                color: #2ecc71;
            }
            .not-hidden-gem {
                color: #e74c3c;
            }
            .reasons {
                margin-top: 20px;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 5px;
            }
        </style>
    </head>
    <body class="bg-gray-100">
        <div class="container mx-auto px-4 py-8">
            <header class="text-center mb-12">
                <h1 class="text-4xl font-bold text-gray-800 mb-4">サウナ穴場チェッカー</h1>
                <p class="text-gray-600">サウナイキタイのレビューから穴場度を分析します</p>
                <div class="mt-4">
                    <a href="/json_ranking" class="text-blue-500 hover:text-blue-700 underline">穴場サウナランキングを見る →</a>
                </div>
            </header>

            <div class="bg-white rounded-lg shadow-md p-6 mb-8">
                <form id="analyze-form" class="space-y-4">
                    <div>
                        <label for="url" class="block text-sm font-medium text-gray-700 mb-2">
                            サウナイキタイの施設ページURLを入力してください
                        </label>
                        <input 
                            type="url" 
                            id="url" 
                            name="url" 
                            placeholder="https://sauna-ikitai.com/saunas/..." 
                            required 
                            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                    </div>
                    <button 
                        type="submit" 
                        class="w-full bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors"
                    >
                        チェック
                    </button>
                </form>
            </div>

            <div id="result" class="bg-white rounded-lg shadow-md p-6 hidden">
                <!-- 結果はJavaScriptで動的に挿入されます -->
            </div>

            <div id="latest-reviews" class="bg-white rounded-lg shadow-md p-6 mt-8">
                <h2 class="text-2xl font-bold mb-4">最新の穴場レビュー</h2>
                <div class="text-sm text-gray-500 mb-4">
                    最終更新: <span id="last-update">-</span>
                </div>
                <button id="refresh-reviews" class="bg-blue-500 text-white px-4 py-2 rounded mb-4">
                    レビューを更新
                </button>
                <div id="reviews-list" class="space-y-4">
                    <!-- レビューはJavaScriptで動的に挿入 -->
                    <p>レビューを取得中...</p>
                </div>
            </div>
        </div>

        <script>
            document.getElementById('analyze-form').onsubmit = async (e) => {
                e.preventDefault();
                const url = document.querySelector('input[name="url"]').value;
                
                // 結果表示部分をリセット
                const resultDiv = document.getElementById('result');
                resultDiv.innerHTML = '<p>データを取得中...</p>';
                resultDiv.classList.remove('hidden');
                
                try {
                    const response = await fetch('/analyze', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: `url=${encodeURIComponent(url)}`
                    });
                    
                    if (!response.ok) {
                        throw new Error(`サーバーエラー: ${response.status}`);
                    }
                    
                    const result = await response.json();
                    
                    if (result.error) {
                        resultDiv.innerHTML = `<p class="text-red-500">${result.error}</p>`;
                    } else {
                        resultDiv.innerHTML = `
                            <h2 class="text-2xl font-bold mb-4">${result.name || 'サウナ情報'}</h2>
                            <p class="score ${result.is_hidden_gem ? 'hidden-gem' : 'not-hidden-gem'} mb-4">
                                穴場度: ${result.score} / ${result.max_score}
                                ${result.is_hidden_gem ? '⭐️ 穴場の可能性が高いです！' : ''}
                            </p>
                            <p class="text-gray-600 mb-4">分析したレビュー数: ${result.review_count}件</p>
                            <div class="reasons">
                                <h3 class="font-semibold mb-2">判定理由:</h3>
                                <ul class="list-disc pl-5">
                                    ${result.reasons.map(reason => `<li>${reason}</li>`).join('')}
                                </ul>
                            </div>
                        `;
                    }
                } catch (error) {
                    console.error('エラー:', error);
                    resultDiv.innerHTML = `<p class="text-red-500">エラーが発生しました: ${error.message}</p>`;
                }
            };

            async function updateLatestReviews() {
                try {
                    const reviewsList = document.getElementById('reviews-list');
                    reviewsList.innerHTML = '<p>レビューを取得中...</p>';
                    
                    const response = await fetch('/api/hidden_gem_reviews');
                    if (!response.ok) {
                        throw new Error(`サーバーエラー: ${response.status}`);
                    }
                    
                    const data = await response.json();
                    
                    if (data.error) {
                        reviewsList.innerHTML = `<p class="text-red-500">${data.error}</p>`;
                        return;
                    }
                    
                    if (!data.hidden_gem_reviews || data.hidden_gem_reviews.length === 0) {
                        reviewsList.innerHTML = '<p>穴場レビューはまだありません。</p>';
                        return;
                    }
                    
                    reviewsList.innerHTML = data.hidden_gem_reviews.map(review => `
                        <div class="border-b border-gray-200 pb-4">
                            <div class="flex justify-between items-center mb-2">
                                <h3 class="font-semibold">${review.name}</h3>
                                <a href="${review.url}" 
                                target="_blank"
                                class="text-blue-500 hover:text-blue-700 text-sm">
                                    詳細を見る →
                                </a>
                            </div>
                            <p class="text-gray-700 text-sm">${review.review.substring(0, 150)}${review.review.length > 150 ? '...' : ''}</p>
                            ${review.keywords ? `<div class="mt-2">
                                <span class="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">キーワード: ${review.keywords.join(', ')}</span>
                            </div>` : ''}
                        </div>
                    `).join('');
                    
                    document.getElementById('last-update').textContent = 
                        new Date().toLocaleString();
                } catch (error) {
                    console.error('レビュー更新エラー:', error);
                    const reviewsList = document.getElementById('reviews-list');
                    reviewsList.innerHTML = `<p class="text-red-500">エラーが発生しました: ${error.message}</p>`;
                }
            }

            // 更新ボタンのイベントリスナー
            document.getElementById('refresh-reviews').addEventListener('click', updateLatestReviews);
            
            // ページ読み込み時に実行
            document.addEventListener('DOMContentLoaded', updateLatestReviews);
        </script>
    </body>
    </html>
    """

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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True) 