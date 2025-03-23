from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
import datetime
import asyncio
import os
from app.services.scraper import SaunaScraper
from app.models.database import init_db, save_review, get_sauna_ranking, get_review_count, get_latest_reviews, get_db, reset_database
import uvicorn
import traceback
from app.tasks import periodic_scraping, get_last_scraping_info, toggle_auto_scraping, reset_scraping_state, start_periodic_scraping, get_scraping_status
from pydantic import BaseModel

app = FastAPI()
scraper = SaunaScraper()

# バックグラウンドタスクの参照を保持するための変数
background_task = None

# 環境変数からプロダクション環境かどうかを判断
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

# リクエストボディのモデル
class ToggleAutoScraping(BaseModel):
    enable: bool

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時にデータベースを初期化"""
    global background_task
    db = get_db()
    await init_db(db)
    # テスト用データを挿入
    # await insert_test_data()  # テストデータ挿入を無効化
    
    if IS_PRODUCTION:
        # プロダクション環境でのみ自動スクレイピングを有効化（ただし即時実行はしない）
        print("プロダクション環境で実行中: 自動スクレイピングが有効化されます")
        # 自動スクレイピングを有効化するだけで、即時実行はしない
        scraping_state["auto_scraping_enabled"] = True
        save_scraping_state()
    else:
        print("開発環境で実行中: 自動スクレイピングは無効化されています")

@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時の処理"""
    global background_task
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            print("バックグラウンドタスクを正常にキャンセルしました")

async def insert_test_data():
    """ランキング表示のためのテストデータを挿入"""
    try:
        # テスト用のサウナデータを追加
        test_saunas = [
            {"id": "sauna1", "name": "東京天然温泉 古代の湯", "review": "穴場サウナです。静かで落ち着いています。"},
            {"id": "sauna2", "name": "サウナしきじ", "review": "都心から離れた隠れた穴場施設。最高でした。"},
            {"id": "sauna3", "name": "カプセルホテル北欧", "review": "意外と空いていて穴場です。"},
            {"id": "sauna4", "name": "サウナ&スパ大東洋", "review": "人が少なくて穴場感があります。"},
            {"id": "sauna5", "name": "天空のアジト マルシンスパ", "review": "絶対的な穴場スポット。誰にも教えたくない。"}
        ]
        
        # 各サウナにテストレビューを追加
        for i, sauna in enumerate(test_saunas):
            # 複数のレビューを追加（人気のものはより多く）
            review_count = 5 - (i % 3)  # 5, 4, 3, 5, 4 のようにレビュー数に差をつける
            
            for j in range(review_count):
                review_id = f"test_{sauna['id']}_{j}"
                await save_review(review_id, sauna['name'], f"{sauna['review']} レビュー{j+1}")
        
        print(f"テストデータを挿入しました")
    except Exception as e:
        print(f"テストデータ挿入中にエラー: {str(e)}")
        print(traceback.format_exc())

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <meta charset="UTF-8">
            <title>サウナ穴場チェッカー - シンプル版</title>
            <style>
                body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                .review { border: 1px solid #ccc; padding: 10px; margin-bottom: 10px; border-radius: 5px; }
                .review h3 { margin-top: 0; }
                .keywords { color: blue; font-size: 0.8em; }
                .buttons { margin: 20px 0; }
                button { padding: 10px; background: #0066ff; color: white; border: none; border-radius: 5px; cursor: pointer; }
                button.secondary { background: #888; }
                button.danger { background: #ff3333; }
                input[type="url"] { width: 80%; padding: 8px; margin-right: 10px; }
                #result { margin-top: 20px; }
                .sauna-name { font-weight: bold; }
                .result-box { border: 1px solid #eee; padding: 15px; background-color: #f9f9f9; border-radius: 5px; }
                .ranking-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
                .ranking-table th, .ranking-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                .ranking-table th { background-color: #f2f2f2; }
                .ranking-table tr:nth-child(even) { background-color: #f9f9f9; }
                .ranking-table tr:hover { background-color: #f5f5f5; }
                .tab-buttons { display: flex; margin-bottom: 15px; }
                .tab-button { padding: 10px 15px; background: #eee; border: none; cursor: pointer; margin-right: 5px; border-radius: 5px 5px 0 0; }
                .tab-button.active { background: #0066ff; color: white; }
                .tab-content { display: none; }
                .tab-content.active { display: block; }
                .status-box { margin-top: 20px; padding: 10px; background-color: #f5f5f5; border-radius: 5px; border: 1px solid #ddd; }
                .auto-status { font-size: 0.9em; color: #666; }
                .admin-panel { margin-top: 20px; padding: 15px; background-color: #f5f5f5; border-radius: 5px; border: 1px solid #ddd; }
                .admin-panel h3 { margin-top: 0; }
                .switch-container { display: flex; align-items: center; margin: 10px 0; }
                .switch { position: relative; display: inline-block; width: 60px; height: 34px; }
                .switch input { opacity: 0; width: 0; height: 0; }
                .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 34px; }
                .slider:before { position: absolute; content: ""; height: 26px; width: 26px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
                input:checked + .slider { background-color: #2196F3; }
                input:checked + .slider:before { transform: translateX(26px); }
                .switch-label { margin-left: 10px; }
                .panel-buttons { margin-top: 10px; }
                .badge { display: inline-block; padding: 3px 8px; border-radius: 10px; font-size: 0.8em; margin-left: 5px; }
                .badge-success { background-color: #28a745; color: white; }
                .badge-danger { background-color: #dc3545; color: white; }
                .badge-warning { background-color: #ffc107; color: black; }
                .badge-info { background-color: #17a2b8; color: white; }
            </style>
        </head>
        <body>
            <h1>サウナ穴場チェッカー</h1>
            
            <div class="tab-buttons">
                <button class="tab-button active" onclick="showTab('check')">穴場チェック</button>
                <button class="tab-button" onclick="showTab('reviews')">最新レビュー</button>
                <button class="tab-button" onclick="showTab('ranking')">穴場ランキング</button>
                <button class="tab-button" onclick="showTab('admin')">管理</button>
            </div>
            
            <div id="check-tab" class="tab-content active">
                <h2>機能1: サウナの穴場度をチェック</h2>
                <form id="analyze-form">
                    <input type="url" id="sauna-url" placeholder="https://sauna-ikitai.com/saunas/..." required>
                    <button type="submit">チェック</button>
                </form>
                <div id="analyze-result" class="result-box"></div>
            </div>
            
            <div id="reviews-tab" class="tab-content">
                <h2>機能2: 最新の穴場レビュー</h2>
                <div class="button-group">
                    <button id="get-reviews">テストレビューを表示</button>
                    <button id="scrape-real" class="primary-button">実サイトからスクレイピング</button>
                </div>
                <div class="note">
                    <small>※実サイトからのスクレイピングは時間がかかることがあります。また、過度なアクセスは避けてください。</small>
                </div>
                <div class="status-box">
                    <div class="auto-status">
                        <strong>自動スクレイピング状態:</strong>
                        <span id="scraping-status">ステータス取得中...</span>
                    </div>
                </div>
                <div id="reviews-result" class="result-box">ボタンをクリックして更新してください</div>
            </div>
            
            <div id="ranking-tab" class="tab-content">
                <h2>機能3: 穴場サウナランキング</h2>
                <button id="get-ranking">ランキングを更新</button>
                <div class="status-box">
                    <div class="auto-status">
                        <strong>自動更新:</strong> レビューが自動的に30分ごとに取得され、ランキングも更新されます。
                        <div>
                            <strong>前回の実行:</strong> <span id="last-scraping">-</span><br>
                            <strong>経過時間:</strong> <span id="time-since-last">-</span><br>
                            <strong>次回実行予定:</strong> <span id="next-scraping">-</span>
                        </div>
                    </div>
                </div>
                <div id="ranking-result" class="result-box">ボタンをクリックして更新してください</div>
            </div>
            
            <div id="admin-tab" class="tab-content">
                <h2>管理機能</h2>
                
                <div class="admin-panel">
                    <h3>スクレイピング設定</h3>
                    
                    <div class="status-details">
                        <p><strong>現在の状態:</strong> <span id="admin-status">取得中...</span></p>
                        <p><strong>前回のスクレイピング:</strong> <span id="admin-last-run">-</span></p>
                        <p><strong>スクレイピング範囲:</strong> 前回 <span id="admin-last-page">-</span> ページまで / 次回 <span id="admin-next-range">-</span></p>
                        <p><strong>総スクレイピングページ数:</strong> <span id="admin-total-pages">-</span></p>
                    </div>
                    
                    <div class="switch-container">
                        <label class="switch">
                            <input type="checkbox" id="auto-scraping-toggle">
                            <span class="slider"></span>
                        </label>
                        <span class="switch-label">自動スクレイピングを有効にする</span>
                    </div>
                    
                    <div class="panel-buttons">
                        <button id="reset-scraping" class="danger">スクレイピング状態をリセット</button>
                        <button id="refresh-status" class="secondary">状態を更新</button>
                    </div>
                </div>
                
                <div class="admin-panel" style="margin-top: 20px;">
                    <h3>データベース管理</h3>
                    <p>データベースをリセットすると、すべてのレビューデータとランキングが削除されます。この操作は元に戻せません。</p>
                    <div class="panel-buttons">
                        <button id="reset-database" class="danger">データベースをリセット</button>
                    </div>
                </div>
            </div>
            
            <script>
                // ページ読み込み時にスクレイピングステータスを取得
                window.addEventListener('load', async () => {
                    await updateScrapingStatus();
                    await updateAdminPanel();
                    // 1分ごとにステータスを更新
                    setInterval(updateScrapingStatus, 60 * 1000);
                });
                
                // スクレイピングステータスを更新する関数
                async function updateScrapingStatus() {
                    try {
                        const response = await fetch('/api/scraping_status');
                        const data = await response.json();
                        
                        if (data.status === 'success') {
                            document.getElementById('scraping-status').textContent = 
                                `自動実行中（30分ごと）- 前回: ${data.data.last_scraping} - 次回: ${data.data.next_scraping}`;
                            document.getElementById('last-scraping').textContent = data.data.last_scraping;
                            document.getElementById('time-since-last').textContent = data.data.time_since_last;
                            document.getElementById('next-scraping').textContent = data.data.next_scraping;
                        } else {
                            document.getElementById('scraping-status').textContent = 'エラーが発生しました';
                        }
                    } catch (error) {
                        document.getElementById('scraping-status').textContent = `エラー: ${error.message}`;
                    }
                }
                
                // 管理パネルを更新する関数
                async function updateAdminPanel() {
                    try {
                        const response = await fetch('/api/scraping_status');
                        const data = await response.json();
                        
                        if (data.status === 'success') {
                            // 状態表示を更新
                            const statusElem = document.getElementById('admin-status');
                            if (data.data.is_running) {
                                statusElem.innerHTML = '実行中 <span class="badge badge-info">スクレイピング中</span>';
                            } else if (data.data.auto_scraping_enabled) {
                                statusElem.innerHTML = '待機中 <span class="badge badge-success">有効</span>';
                            } else {
                                statusElem.innerHTML = '停止 <span class="badge badge-danger">無効</span>';
                            }
                            
                            // トグルスイッチを更新
                            document.getElementById('auto-scraping-toggle').checked = data.data.auto_scraping_enabled;
                            
                            // 各種情報を更新
                            document.getElementById('admin-last-run').textContent = data.data.last_scraping;
                            document.getElementById('admin-last-page').textContent = data.data.last_page;
                            document.getElementById('admin-next-range').textContent = data.data.next_page_range;
                            document.getElementById('admin-total-pages').textContent = data.data.total_pages_scraped;
                        }
                    } catch (error) {
                        console.error('管理パネル更新エラー:', error);
                    }
                }
                
                // 自動スクレイピングトグルのイベントリスナー
                document.getElementById('auto-scraping-toggle').addEventListener('change', async (e) => {
                    try {
                        const enabled = e.target.checked;
                        const response = await fetch('/api/toggle_auto_scraping', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({ enable: enabled })
                        });
                        
                        const data = await response.json();
                        if (data.status === 'success') {
                            alert(data.data.message);
                            await updateAdminPanel();
                        } else {
                            alert(`エラー: ${data.message}`);
                            // エラー時は元の状態に戻す
                            e.target.checked = !enabled;
                        }
                    } catch (error) {
                        alert(`エラー: ${error.message}`);
                        e.target.checked = !e.target.checked;
                    }
                });
                
                // スクレイピング状態リセットボタンのイベントリスナー
                document.getElementById('reset-scraping').addEventListener('click', async () => {
                    if (confirm('スクレイピング状態をリセットしますか？次回のスクレイピングは1ページ目から開始されます。')) {
                        try {
                            const response = await fetch('/api/reset_scraping', {
                                method: 'POST'
                            });
                            
                            const data = await response.json();
                            if (data.status === 'success') {
                                alert(data.data.message);
                                await updateAdminPanel();
                            } else {
                                alert(`エラー: ${data.message}`);
                            }
                        } catch (error) {
                            alert(`エラー: ${error.message}`);
                        }
                    }
                });
                
                // 状態更新ボタンのイベントリスナー
                document.getElementById('refresh-status').addEventListener('click', updateAdminPanel);
                
                // データベースリセットボタンのイベントリスナー
                document.getElementById('reset-database').addEventListener('click', async () => {
                    if (confirm('本当にデータベースをリセットしますか？すべてのレビューとランキングデータが削除されます。この操作は元に戻せません。')) {
                        try {
                            const response = await fetch('/api/reset_database', {
                                method: 'POST'
                            });
                            
                            const data = await response.json();
                            if (data.status === 'success') {
                                alert(data.message);
                                // ランキング表示を更新（表示中の場合）
                                if (document.getElementById('ranking-tab').classList.contains('active')) {
                                    document.getElementById('get-ranking').click();
                                }
                            } else {
                                alert(`エラー: ${data.message}`);
                            }
                        } catch (error) {
                            alert(`エラー: ${error.message}`);
                        }
                    }
                });
                
                // タブ切り替え機能
                function showTab(tabName) {
                    // すべてのタブコンテンツを非表示
                    document.querySelectorAll('.tab-content').forEach(tab => {
                        tab.classList.remove('active');
                    });
                    
                    // すべてのタブボタンの active クラスを削除
                    document.querySelectorAll('.tab-button').forEach(button => {
                        button.classList.remove('active');
                    });
                    
                    // 選択したタブとボタンをアクティブに
                    document.getElementById(tabName + '-tab').classList.add('active');
                    document.querySelector(`.tab-button[onclick="showTab('${tabName}')"]`).classList.add('active');
                    
                    // 管理タブが選択された場合は状態を更新
                    if (tabName === 'admin') {
                        updateAdminPanel();
                    }
                }
                
                document.getElementById('analyze-form').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const url = document.getElementById('sauna-url').value;
                    const resultDiv = document.getElementById('analyze-result');
                    
                    resultDiv.textContent = '分析中...';
                    
                    try {
                        const response = await fetch('/api/analyze', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded',
                            },
                            body: `url=${encodeURIComponent(url)}`
                        });
                        
                        const data = await response.json();
                        
                        if (data.error) {
                            resultDiv.innerHTML = `<p style="color: red">エラー: ${data.error}</p>`;
                        } else {
                            let html = `
                                <h3>${data.name || 'サウナ情報'}</h3>
                                <p>穴場度: ${data.score} / ${data.max_score}</p>
                                <p>判定: ${data.is_hidden_gem ? '⭐️ 穴場の可能性が高いです！' : '穴場度は低いようです'}</p>
                                <p>分析レビュー数: ${data.review_count}件</p>
                                <h4>判定理由:</h4>
                                <ul>
                            `;
                            
                            data.reasons.forEach(reason => {
                                html += `<li>${reason}</li>`;
                            });
                            
                            html += `</ul>`;
                            resultDiv.innerHTML = html;
                        }
                    } catch (error) {
                        resultDiv.innerHTML = `<p style="color: red">エラー: ${error.message}</p>`;
                    }
                });
                
                document.getElementById('get-reviews').addEventListener('click', async () => {
                    const resultDiv = document.getElementById('reviews-result');
                    resultDiv.textContent = 'レビュー取得中...';
                    
                    try {
                        const response = await fetch('/api/hidden_gem_reviews');
                        const data = await response.json();
                        
                        if (data.error) {
                            resultDiv.innerHTML = `<p style="color: red">エラー: ${data.error}</p>`;
                            return;
                        }
                        
                        if (!data.hidden_gem_reviews || data.hidden_gem_reviews.length === 0) {
                            resultDiv.innerHTML = '<p>穴場レビューはまだありません</p>';
                            return;
                        }
                        
                        let html = `<p>取得時刻: ${new Date().toLocaleString()}</p>`;
                        
                        data.hidden_gem_reviews.forEach(review => {
                            html += `
                                <div class="review">
                                    <h3 class="sauna-name">${review.name}</h3>
                                    <p>${review.review}</p>
                                    <p class="keywords">キーワード: ${review.keywords ? review.keywords.join(', ') : 'なし'}</p>
                                </div>
                            `;
                        });
                        
                        resultDiv.innerHTML = html;
                    } catch (error) {
                        resultDiv.innerHTML = `<p style="color: red">エラー: ${error.message}</p>`;
                    }
                });
                
                document.getElementById('scrape-real').addEventListener('click', async () => {
                    const resultDiv = document.getElementById('reviews-result');
                    resultDiv.textContent = '実サイトからレビュー取得中...（少し時間がかかります）';
                    
                    try {
                        const response = await fetch('/api/scrape_real');
                        const data = await response.json();
                        
                        if (data.error) {
                            resultDiv.innerHTML = `<p style="color: red">エラー: ${data.error}</p>`;
                            return;
                        }
                        
                        if (!data.reviews || data.reviews.length === 0) {
                            resultDiv.innerHTML = '<p>穴場レビューは見つかりませんでした</p>';
                            return;
                        }
                        
                        let html = `<p>取得時刻: ${new Date().toLocaleString()}</p>`;
                        html += `<p>${data.message}</p>`;
                        
                        // レビュー一覧を表示
                        data.reviews.forEach(review => {
                            html += `
                                <div class="review">
                                    <h3 class="sauna-name">
                                        <a href="${review.url}" target="_blank">${review.name}</a>
                                    </h3>
                                    <p>${review.review}</p>
                                    <p class="keywords">キーワード: ${review.keywords ? review.keywords.join(', ') : 'なし'}</p>
                                </div>
                            `;
                        });
                        
                        // ランキングデータがある場合、ランキングタブのデータも更新
                        if (data.ranking && data.ranking.length > 0) {
                            const rankingDiv = document.getElementById('ranking-result');
                            let rankingHtml = `
                                <p>取得時刻: ${new Date().toLocaleString()}</p>
                                <p>総レビュー数: ${data.total_reviews}件 / 総サウナ数: ${data.total_saunas}件</p>
                                <table class="ranking-table">
                                    <thead>
                                        <tr>
                                            <th>順位</th>
                                            <th>サウナ名</th>
                                            <th>レビュー数</th>
                                            <th>最終更新</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                            `;
                            
                            data.ranking.forEach((sauna, index) => {
                                const date = new Date(sauna.last_updated).toLocaleString();
                                rankingHtml += `
                                    <tr>
                                        <td>${index + 1}</td>
                                        <td>${sauna.name}</td>
                                        <td>${sauna.review_count}</td>
                                        <td>${date}</td>
                                    </tr>
                                `;
                            });
                            
                            rankingHtml += `
                                    </tbody>
                                </table>
                                <p><small>※スクレイピングにより自動更新されました</small></p>
                            `;
                            
                            rankingDiv.innerHTML = rankingHtml;
                            
                            // 成功メッセージをレビュー結果に追加
                            html += `
                                <div class="success-message" style="margin-top: 20px; padding: 10px; background-color: #e6f7e6; border-radius: 5px; border: 1px solid #c3e6c3;">
                                    <p><strong>ランキングも自動的に更新されました！</strong></p>
                                    <p>「穴場ランキング」タブで最新のランキングを確認できます。</p>
                                </div>
                            `;
                        }
                        
                        resultDiv.innerHTML = html;
                    } catch (error) {
                        resultDiv.innerHTML = `<p style="color: red">エラー: ${error.message}</p>`;
                    }
                });
                
                document.getElementById('get-ranking').addEventListener('click', async () => {
                    const resultDiv = document.getElementById('ranking-result');
                    resultDiv.textContent = 'ランキング取得中...';
                    
                    try {
                        const response = await fetch('/api/ranking');
                        const data = await response.json();
                        
                        if (data.error) {
                            resultDiv.innerHTML = `<p style="color: red">エラー: ${data.error}</p>`;
                            return;
                        }
                        
                        if (!data.ranking || data.ranking.length === 0) {
                            resultDiv.innerHTML = '<p>ランキングデータはまだありません</p>';
                            return;
                        }
                        
                        let html = `
                            <p>取得時刻: ${new Date().toLocaleString()}</p>
                            <p>総レビュー数: ${data.total_reviews}件 / 総サウナ数: ${data.total_saunas}件</p>
                            <table class="ranking-table">
                                <thead>
                                    <tr>
                                        <th>順位</th>
                                        <th>サウナ名</th>
                                        <th>レビュー数</th>
                                        <th>最終更新</th>
                                    </tr>
                                </thead>
                                <tbody>
                        `;
                        
                        data.ranking.forEach((sauna, index) => {
                            const date = new Date(sauna.last_updated).toLocaleString();
                            html += `
                                <tr>
                                    <td>${index + 1}</td>
                                    <td>${sauna.name}</td>
                                    <td>${sauna.review_count}</td>
                                    <td>${date}</td>
                                </tr>
                            `;
                        });
                        
                        html += `
                                </tbody>
                            </table>
                        `;
                        
                        resultDiv.innerHTML = html;
                    } catch (error) {
                        resultDiv.innerHTML = `<p style="color: red">エラー: ${error.message}</p>`;
                    }
                });
            </script>
        </body>
    </html>
    """

@app.post("/api/analyze")
async def analyze(url: str = Form(...)):
    try:
        result = await scraper.analyze_sauna(url)
        return result
    except Exception as e:
        return {"error": f"エラーが発生しました: {str(e)}"}

@app.get("/api/hidden_gem_reviews")
async def get_hidden_gem_reviews():
    try:
        # テストファイルからのレビュー取得を使用
        reviews = await scraper.get_hidden_gem_reviews_test()
        
        if not reviews or len(reviews) == 0:
            print("テストファイルからレビューが取得できませんでした")
            # テストレビューが取得できない場合は、データベースから既存のレビューを取得
            db_reviews = await get_latest_reviews(limit=10)
            
            # データベースのレビューを適切な形式に変換
            reviews = [
                {
                    "name": review["sauna_name"],
                    "review": review["review_text"],
                    "keywords": ["穴場"],  # 実際のキーワードはデータベースから取得できないため、固定値を使用
                    "url": f"https://sauna-ikitai.com/saunas/{review['sauna_name'].replace(' ', '_')}"  # 実際のURLは保存されていないため、仮のURLを生成
                }
                for review in db_reviews
            ]
            
        return {"hidden_gem_reviews": reviews}
    except Exception as e:
        print(f"レビュー取得中にエラー発生: {str(e)}")
        print(traceback.format_exc())
        return {"error": str(e), "hidden_gem_reviews": []}

@app.get("/api/ranking")
async def get_ranking():
    try:
        ranking = await get_sauna_ranking(limit=20)
        total_reviews = await get_review_count()
        return {
            "ranking": ranking,
            "total_reviews": total_reviews,
            "total_saunas": len(ranking)
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/test/scraping")
async def test_scraping():
    """テスト用スクレイピングエンドポイント"""
    try:
        reviews = await scraper.get_hidden_gem_reviews_test()
        print(f"取得したレビュー数: {len(reviews)}")
        
        # サウナごとの穴場カウントを集計
        sauna_counts = {}
        for review in reviews:
            sauna_name = review["name"]
            if sauna_name not in sauna_counts:
                sauna_counts[sauna_name] = {
                    "count": 0,
                    "url": review["url"],
                    "reviews": [],
                    "keywords": set()
                }
            sauna_counts[sauna_name]["count"] += 1
            sauna_counts[sauna_name]["reviews"].append(review["review"])
            
            # レビュー内のキーワードを抽出
            for keyword in ["穴場", "hidden", "隠れた"]:
                if keyword in review["review"]:
                    sauna_counts[sauna_name]["keywords"].add(keyword)
        
        # ランキング形式でソート
        ranking = []
        for name, data in sauna_counts.items():
            keywords_list = list(data["keywords"])
            ranking.append({
                "name": name,
                "url": data["url"],
                "review_count": data["count"],
                "keywords": keywords_list,
                "keyword_count": len(keywords_list),
                "reviews": data["reviews"][:3]  # 最新3件のみを表示
            })
        
        # レビュー数とキーワード数で降順ソート
        ranking.sort(key=lambda x: (x["review_count"], x["keyword_count"]), reverse=True)
        
        return {
            "status": "success",
            "message": f"{len(reviews)}件のテストレビューを取得しました",
            "total_saunas": len(ranking),
            "ranking": ranking
        }
    except Exception as e:
        print(f"ランキング処理中にエラー発生: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/api/scrape_real")
async def scrape_real_reviews():
    """実サイトからレビューをスクレイピングするエンドポイント"""
    try:
        # 実サイトからのスクレイピングを実行
        reviews = await scraper.get_hidden_gem_reviews(max_pages=3)
        
        # スクレイピング後のランキングを取得
        ranking = await get_sauna_ranking(limit=20)
        total_reviews = await get_review_count()
        
        return {
            "status": "success",
            "message": f"{len(reviews)}件の穴場レビューを取得しました",
            "reviews": reviews[:10],  # 最新10件のみ返す
            "ranking": ranking,
            "total_reviews": total_reviews,
            "total_saunas": len(ranking)
        }
    except Exception as e:
        print(f"実サイトスクレイピング中にエラー: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/api/scraping_status")
async def scraping_status():
    return await get_scraping_status()

@app.post("/api/toggle_auto_scraping")
async def toggle_auto_scraping_endpoint(toggle_data: ToggleAutoScraping, background_tasks: BackgroundTasks):
    return await toggle_auto_scraping(toggle_data.enable, background_tasks)

@app.get("/api/github-action-scraping")
async def github_action_scraping():
    """GitHub Actionsから呼び出される定期実行用のエンドポイント"""
    try:
        from app.tasks import load_scraping_state, scraping_state, save_scraping_state
        load_scraping_state()

        start_page = scraping_state.get('last_page', 0) + 1
        end_page = start_page + 2  # 3ページずつ

        if start_page <= 0:
            start_page = 1
            end_page = 3

        scraping_state['is_running'] = True
        save_scraping_state()

        reviews = await scraper.get_hidden_gem_reviews(
            max_pages=3,
            start_page=start_page,
            end_page=end_page
        )

        scraping_state['last_page'] = end_page
        scraping_state['last_run'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        scraping_state['total_pages_scraped'] = scraping_state.get('total_pages_scraped', 0) + (end_page - start_page + 1)
        scraping_state['is_running'] = False
        save_scraping_state()

        return {
            "status": "success",
            "message": f"{len(reviews)}件のレビューを取得しました",
            "current_page_range": f"{start_page}〜{end_page}",
            "next_page_range": f"{end_page + 1}〜{end_page + 3}"
        }
    except Exception as e:
        import traceback
        scraping_state['is_running'] = False
        save_scraping_state()
        print("GitHub Action スクレイピング中にエラー:", str(e))
        print(traceback.format_exc())
        return {
            "status": "error",
            "message": f"スクレイピングに失敗しました: {str(e)}"
        }

@app.post("/api/reset_scraping")
async def reset_scraping_endpoint():
    return await reset_scraping_state()

@app.post("/api/reset_database")
async def reset_database_endpoint():
    """データベースをリセットするエンドポイント"""
    try:
        result = await reset_database()
        if result:
            return {"status": "success", "message": "データベースが正常にリセットされました"}
        return {"status": "error", "message": "データベースのリセットに失敗しました"}
    except Exception as e:
        print(f"データベースリセット中にエラー: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": f"エラーが発生しました: {str(e)}"}

if __name__ == "__main__":
    # 環境変数からポート番号を取得するか、デフォルト値を使用
    port = int(os.getenv("PORT", 9000))
    
    # 環境に応じてホストを設定
    # 重要: 0.0.0.0を使用して全てのネットワークインターフェイスでリッスンする
    host = "0.0.0.0"
    
    # サーバーを起動
    uvicorn.run(app, host=host, port=port, reload=not IS_PRODUCTION) 