from datetime import datetime
import os
from pathlib import Path
import asyncio
import time
from datetime import datetime, timedelta
import traceback
import json
from app.services.scraper import SaunaScraper
from app.models.database import get_db, save_review
from app.database import save_reviews

from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse

# スクレイパーのインスタンスを作成
scraper = SaunaScraper()

# 前回のスクレイピング時刻を記録する変数
last_scraping_time = None

# 環境変数
IS_RENDER = os.environ.get('RENDER', 'False') == 'True'

# データディレクトリの設定
if IS_RENDER:
    DATA_DIR = Path('/opt/render/project/src/data')
else:
    DATA_DIR = Path('./data')

# スクレイピング状態を保存するファイルパス
SCRAPING_STATE_FILE = DATA_DIR / 'scraping_state.json'

# スクレイピングの状態管理用の辞書
scraping_state = {
    "last_page": 0,  # 最後にスクレイピングしたページ
    "total_pages_scraped": 0,  # スクレイピングした総ページ数
    "last_run": None,  # 最後に実行した時刻
    "is_running": False,  # 現在実行中かどうか
    "auto_scraping_enabled": True,  # 自動スクレイピングが有効かどうか
    "next_scraping": None  # 次回スクレイピングの予定時刻
}

# データディレクトリが存在しない場合は作成
def ensure_data_dir():
    """データディレクトリの存在を確認し、必要に応じて作成する"""
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(exist_ok=True)
        print(f"データディレクトリを作成しました: {DATA_DIR}")
    else:
        print(f"データディレクトリを確認しました: {DATA_DIR}")
    
    return DATA_DIR

def load_scraping_state():
    """スクレイピング状態を読み込む"""
    global scraping_state
    
    try:
        # データディレクトリの確保
        ensure_data_dir()
        
        # スクレイピング状態ファイルが存在するか確認
        if SCRAPING_STATE_FILE.exists():
            with open(SCRAPING_STATE_FILE, 'r', encoding='utf-8') as f:
                loaded_state = json.load(f)
                scraping_state.update(loaded_state)
                
            print(f"スクレイピング状態を読み込みました: {SCRAPING_STATE_FILE}")
        else:
            # ファイルが存在しない場合はデフォルト状態を設定
            scraping_state = {
                "last_page": 0,
                "total_pages_scraped": 0,
                "is_running": False,
                "auto_scraping_enabled": True,
                "last_run": "",
                "next_scraping": (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
            }
            print(f"スクレイピング状態ファイルが見つからないため、デフォルト状態を使用します")
            
            # デフォルト状態を保存
            save_scraping_state()
    
    except Exception as e:
        print(f"スクレイピング状態の読み込みに失敗しました: {str(e)}")
        print(traceback.format_exc())
        
        # エラー時はデフォルト状態を設定
        scraping_state = {
            "last_page": 0,
            "total_pages_scraped": 0,
            "is_running": False,
            "auto_scraping_enabled": True,
            "last_run": "",
            "next_scraping": (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        }

def save_scraping_state():
    """スクレイピング状態を保存する"""
    global scraping_state
    
    try:
        # データディレクトリの確保
        ensure_data_dir()
        
        # 状態をJSONファイルとして保存
        with open(SCRAPING_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(scraping_state, f, ensure_ascii=False, indent=2)
            
        print(f"スクレイピング状態を保存しました: {SCRAPING_STATE_FILE}")
    
    except Exception as e:
        print(f"スクレイピング状態の保存に失敗しました: {str(e)}")
        print(traceback.format_exc())

async def toggle_auto_scraping(enable=None):
    """自動スクレイピングの有効/無効を切り替える"""
    global scraping_state
    
    try:
        # 現在のスクレイピング状態を読み込む
        load_scraping_state()
        
        if enable is not None:
            scraping_state["auto_scraping_enabled"] = enable
        else:
            # 指定がなければ現在の状態を反転
            scraping_state["auto_scraping_enabled"] = not scraping_state["auto_scraping_enabled"]
        
        # 有効にした場合は次回実行時刻を設定
        if scraping_state["auto_scraping_enabled"]:
            next_run_time = datetime.now() + timedelta(minutes=15)
            scraping_state["next_scraping"] = next_run_time.strftime('%Y-%m-%d %H:%M:%S')
        
        save_scraping_state()
        
        message = f"自動スクレイピングを{'有効' if scraping_state['auto_scraping_enabled'] else '無効'}にしました"
        print(message)
        
        # 結果を返す
        return {
            "status": "success",
            "auto_scraping_enabled": scraping_state["auto_scraping_enabled"],
            "message": message,
            "next_scraping": scraping_state.get("next_scraping", "未定")
        }
    except Exception as e:
        # エラー発生時
        print(f"自動スクレイピング設定エラー: {str(e)}")
        print(traceback.format_exc())
        
        # エラーを返す
        return {
            "status": "error",
            "message": f"設定の変更に失敗しました: {str(e)}"
        }

async def reset_scraping_state():
    """スクレイピング状態をリセットする"""
    global scraping_state
    
    try:
        # 初期状態を設定
        scraping_state = {
            "last_page": 0,
            "total_pages_scraped": 0,
            "is_running": False,
            "auto_scraping_enabled": True,
            "last_run": "",
            "next_scraping": (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 状態を保存
        save_scraping_state()
        
        message = "スクレイピング状態をリセットしました。次回は最初のページからスクレイピングが開始されます。"
        print(message)
        
        # 結果を返す
        return {
            "status": "success",
            "message": message,
            "data": scraping_state
        }
    
    except Exception as e:
        # エラー発生時
        error_message = f"スクレイピング状態のリセットに失敗しました: {str(e)}"
        print(error_message)
        print(traceback.format_exc())
        
        # エラーを返す
        return {
            "status": "error",
            "message": error_message
        }

async def periodic_scraping(background_tasks=None):
    """周期的スクレイピング処理"""
    global scraping_state
    
    try:
        # データディレクトリの確保
        ensure_data_dir()
        
        # スクレイピング状態を読み込む
        load_scraping_state()
        
        # 既に実行中の場合は何もしない
        if scraping_state.get("is_running", False):
            message = "スクレイピングは既に実行中です。"
            print(message)
            
            # APIからの呼び出しの場合はJSONResponseを返す
            if background_tasks is not None:
                return JSONResponse(
                    content={"status": "info", "message": message}
                )
            return {"message": message, "status": "info"}
        
        # 実行中フラグを設定
        scraping_state["is_running"] = True
        save_scraping_state()
        
        print("スクレイピングを開始します...")
        
        # 開始ページと終了ページを決定
        start_page = int(scraping_state.get("last_page", 0)) + 1
        end_page = start_page + 2  # 1回の実行で3ページをスクレイピング
        
        # スクレイピングを実行
        base_url = "https://sauna-ikitai.com/posts?prefecture%5B%5D=tokyo&keyword=%E7%A9%B4%E5%A0%B4"
        results = await scraper.scrape_sauna_reviews(base_url=base_url, start_page=start_page, end_page=end_page)
        
        # 結果を保存
        if results:
            num_saved = await save_reviews(results)
            print(f"{num_saved}件のレビューをデータベースに保存しました")
        else:
            num_saved = 0
            print("保存するレビューがありませんでした")
        
        # スクレイピング状態を更新
        scraping_state["is_running"] = False
        scraping_state["last_page"] = end_page
        scraping_state["total_pages_scraped"] += (end_page - start_page + 1)
        scraping_state["last_run"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 次回のスクレイピング時刻を15分後に設定
        next_run_time = datetime.now() + timedelta(minutes=15)
        scraping_state["next_scraping"] = next_run_time.strftime('%Y-%m-%d %H:%M:%S')
        
        save_scraping_state()
        
        # 結果メッセージを作成
        message = f"スクレイピングが完了しました。ページ {start_page} から {end_page} まで処理し、{num_saved} 件のレビューを保存しました。"
        print(message)
        
        # APIからの呼び出しの場合はJSONResponseを返す
        if background_tasks is not None:
            return JSONResponse(
                content={
                    "status": "success", 
                    "message": message,
                    "data": {
                        "start_page": start_page,
                        "end_page": end_page,
                        "reviews_saved": num_saved,
                        "next_scraping": scraping_state["next_scraping"]
                    }
                }
            )
        
        # 通常の呼び出しの場合は辞書を返す
        return {
            "message": message,
            "start_page": start_page,
            "end_page": end_page,
            "reviews_saved": num_saved,
            "next_scraping": scraping_state["next_scraping"]
        }
        
    except Exception as e:
        # エラー発生時
        print(f"スクレイピングエラー: {str(e)}")
        print(traceback.format_exc())
        
        # スクレイピング状態をリセット
        scraping_state["is_running"] = False
        save_scraping_state()
        
        # APIからの呼び出しの場合はJSONResponseでエラーを返す
        if background_tasks is not None:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"スクレイピングに失敗しました: {str(e)}"}
            )
        
        # 通常の呼び出しの場合は辞書でエラーを返す
        return {
            "message": f"エラー: {str(e)}",
            "error": True
        }

# 起動時に状態を読み込む
load_scraping_state() 