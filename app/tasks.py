import asyncio
import time
from datetime import datetime, timedelta
import traceback
import json
import os
from pathlib import Path
from app.services.scraper import SaunaScraper
from app.models.database import get_sauna_ranking, get_review_count, get_db, save_review, init_db
from app.database import save_reviews

from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse

# スクレイパーのインスタンスを作成
scraper = SaunaScraper()

# 前回のスクレイピング時刻を記録する変数
last_scraping_time = None

# Render環境かどうかを確認
IS_RENDER = os.environ.get('RENDER', 'False') == 'True'

# スクレイピング状態を保存するファイルパス
if IS_RENDER:
    # Render環境では永続的なデータディレクトリを使用
    DATA_DIR = Path('/opt/render/project/src/data')
    SCRAPING_STATE_FILE = DATA_DIR / 'scraping_state.json'
    print(f"Render環境での状態ファイル: {SCRAPING_STATE_FILE}")
else:
    # ローカル環境ではプロジェクトディレクトリに状態ファイルを保存
    DATA_DIR = Path('.')
    SCRAPING_STATE_FILE = Path('scraping_state.json')
    print(f"ローカル環境での状態ファイル: {SCRAPING_STATE_FILE}")

# スクレイピングの状態管理用の辞書
scraping_state = {
    "last_page": 0,  # 最後にスクレイピングしたページ
    "total_pages_scraped": 0,  # スクレイピングした総ページ数
    "last_run": None,  # 最後に実行した時刻
    "is_running": False,  # 現在実行中かどうか
    "auto_scraping_enabled": False,  # 自動スクレイピングが有効かどうか
    "next_scraping": None  # 次回スクレイピングの予定時刻
}

def load_scraping_state():
    """スクレイピング状態を読み込む"""
    global scraping_state
    
    try:
        # スクレイピング状態ファイルのパスを決定
        if IS_RENDER:
            # Render環境では永続的なデータディレクトリを使用
            data_dir = "/opt/render/project/src/data"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir, exist_ok=True)
                print(f"Created persistent data directory for state: {data_dir}")
            
            state_file_path = os.path.join(data_dir, "scraping_state.json")
        else:
            # ローカル環境では現在の作業ディレクトリを使用
            state_file_path = "scraping_state.json"
        
        # ファイルが存在するか確認
        if os.path.exists(state_file_path):
            with open(state_file_path, 'r', encoding='utf-8') as f:
                loaded_state = json.load(f)
                scraping_state.update(loaded_state)
                
            # 古いキー名を新しいキー名に変換（互換性のため）
            if "last_page" in scraping_state and "last_scraped_page" not in scraping_state:
                scraping_state["last_scraped_page"] = scraping_state.pop("last_page")
                
            if "total_pages_scraped" in scraping_state and "total_scraped_pages" not in scraping_state:
                scraping_state["total_scraped_pages"] = scraping_state.pop("total_pages_scraped")
                
            print(f"スクレイピング状態を読み込みました: {state_file_path}")
        else:
            # ファイルが存在しない場合はデフォルト状態を設定
            scraping_state = {
                "last_scraped_page": 0,
                "total_scraped_pages": 0,
                "is_running": False,
                "auto_scraping_enabled": True,  # GitHub Actionsは15分毎に実行
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
            "last_scraped_page": 0,
            "total_scraped_pages": 0,
            "is_running": False,
            "auto_scraping_enabled": True,  # GitHub Actionsは15分毎に実行
            "last_run": "",
            "next_scraping": (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        }

def save_scraping_state():
    """スクレイピング状態を保存する"""
    global scraping_state
    
    try:
        # スクレイピング状態ファイルのパスを決定
        if IS_RENDER:
            # Render環境では永続的なデータディレクトリを使用
            data_dir = "/opt/render/project/src/data"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir, exist_ok=True)
                print(f"Created persistent data directory for state: {data_dir}")
            
            state_file_path = os.path.join(data_dir, "scraping_state.json")
        else:
            # ローカル環境では現在の作業ディレクトリを使用
            state_file_path = "scraping_state.json"
        
        # 状態をJSONファイルとして保存
        with open(state_file_path, 'w', encoding='utf-8') as f:
            json.dump(scraping_state, f, ensure_ascii=False, indent=2)
            
        print(f"スクレイピング状態を保存しました: {state_file_path}")
    
    except Exception as e:
        print(f"スクレイピング状態の保存に失敗しました: {str(e)}")
        print(traceback.format_exc())

async def periodic_scraping(background_tasks=None):
    """周期的スクレイピング処理
    
    Note: この関数はUIからの手動スクレイピングと、GitHub Actionsからの呼び出しの両方に対応
    """
    global scraping_state
    
    try:
        # データベース接続を確認
        data_dir = "/opt/render/project/src/data"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            print(f"Created persistent data directory: {data_dir}")
        
        db_path = os.path.join(data_dir, "sauna_temp.db")
        print(f"Using database at: {db_path}")
        
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
        
        # スクレイパーを初期化
        scraper = SaunaScraper()
        
        # 開始ページと終了ページを決定
        start_page = int(scraping_state.get("last_scraped_page", 0)) + 1
        end_page = start_page + 3  # 1回の実行で3ページをスクレイピング
        
        # スクレイピングを実行
        results = await scraper.scrape_sauna_reviews(start_page, end_page)
        
        # 結果を保存（非同期関数）
        num_saved = await save_reviews(results)
        
        # スクレイピング状態を更新
        scraping_state["is_running"] = False
        scraping_state["last_scraped_page"] = end_page
        scraping_state["total_scraped_pages"] += (end_page - start_page + 1)
        scraping_state["last_run"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 次回のスクレイピング時刻を15分後に設定（GitHub Actionsのスケジュールに合わせる）
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

# スクレイピングタスクを開始する関数
async def start_periodic_scraping():
    """単発のスクレイピングタスクを実行する"""
    # 実行中の場合は何もしない
    if scraping_state["is_running"]:
        print("スクレイピングは既に実行中です。")
        return

    # 単発実行
    print("スクレイピングタスクを実行します。")
    await periodic_scraping()

async def get_last_scraping_info():
    """最後のスクレイピング情報を取得する関数"""
    global scraping_state
    
    # 現在のスクレイピング状態を読み込む
    if not SCRAPING_STATE_FILE.exists():
        load_scraping_state()
    
    if last_scraping_time:
        time_diff = datetime.now() - last_scraping_time
        minutes = time_diff.seconds // 60
        seconds = time_diff.seconds % 60
        
        next_scraping_minutes = max(0, 30 - minutes)
        
        return {
            "last_scraping": last_scraping_time.strftime("%Y-%m-%d %H:%M:%S"),
            "time_since_last": f"{minutes}分{seconds}秒前",
            "next_scraping": f"約{next_scraping_minutes}分後",
            "last_page": scraping_state["last_page"],
            "total_pages_scraped": scraping_state["total_pages_scraped"],
            "next_page_range": f"{scraping_state['last_page'] + 1}〜{scraping_state['last_page'] + 3}",
            "auto_scraping_enabled": scraping_state["auto_scraping_enabled"],
            "is_running": scraping_state["is_running"]
        }
    else:
        return {
            "last_scraping": scraping_state.get("last_run", "まだ実行されていません"),
            "time_since_last": "N/A",
            "next_scraping": "まもなく実行されます",
            "last_page": scraping_state["last_page"],
            "total_pages_scraped": scraping_state["total_pages_scraped"],
            "next_page_range": f"{scraping_state['last_page'] + 1}〜{scraping_state['last_page'] + 3}",
            "auto_scraping_enabled": scraping_state["auto_scraping_enabled"],
            "is_running": scraping_state["is_running"]
        }

async def toggle_auto_scraping(enable=None, background_tasks=None):
    """自動スクレイピングの有効/無効を切り替える
    
    Note: この機能はGitHub Actionsによる自動スクレイピングに置き換えられていますが、
    UIとの互換性のために残しています。実際にはGitHub Actionsのスケジュール実行が使用されます。
    """
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
        
        message = f"自動スクレイピングを{'有効' if scraping_state['auto_scraping_enabled'] else '無効'}にしました（GitHub Actionsで15分ごとに実行）"
        
        # APIからの呼び出しの場合はJSONResponseを返す
        if background_tasks is not None:
            return JSONResponse(content={
                "status": "success",
                "data": {
                    "enabled": scraping_state["auto_scraping_enabled"],
                    "message": message,
                    "next_scraping": scraping_state.get("next_scraping", "未定")
                }
            })
        
        # 通常の呼び出しの場合は辞書を返す
        return {
            "auto_scraping_enabled": scraping_state["auto_scraping_enabled"],
            "message": message,
            "next_scraping": scraping_state.get("next_scraping", "未定")
        }
    except Exception as e:
        # エラー発生時
        print(f"自動スクレイピング設定エラー: {str(e)}")
        print(traceback.format_exc())
        
        # APIからの呼び出しの場合はJSONResponseでエラーを返す
        if background_tasks is not None:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"設定の変更に失敗しました: {str(e)}"}
            )
        
        # 通常の呼び出しの場合は辞書でエラーを返す
        return {
            "auto_scraping_enabled": False,
            "message": f"エラー: {str(e)}",
            "error": True
        }

async def reset_scraping_state(background_tasks=None):
    """スクレイピング状態をリセットする
    
    Note: この関数はUIからのリセット操作とGitHub Actionsとの連携の両方に対応
    """
    global scraping_state
    
    try:
        # 初期状態を設定
        scraping_state = {
            "last_scraped_page": 0,
            "total_scraped_pages": 0,
            "is_running": False,
            "auto_scraping_enabled": True,  # GitHub Actionsは15分毎に実行
            "last_run": "",
            "next_scraping": (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 状態を保存
        save_scraping_state()
        
        message = "スクレイピング状態をリセットしました。次回は最初のページからスクレイピングが開始されます。"
        print(message)
        
        # APIからの呼び出しの場合はJSONResponseを返す
        if background_tasks is not None:
            return JSONResponse(
                content={
                    "status": "success", 
                    "message": message,
                    "data": scraping_state
                }
            )
        
        # 通常の呼び出しの場合は辞書を返す
        return {
            "message": message,
            "status": "success",
            "data": scraping_state
        }
    
    except Exception as e:
        # エラー発生時
        error_message = f"スクレイピング状態のリセットに失敗しました: {str(e)}"
        print(error_message)
        print(traceback.format_exc())
        
        # APIからの呼び出しの場合はJSONResponseでエラーを返す
        if background_tasks is not None:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": error_message}
            )
        
        # 通常の呼び出しの場合は辞書でエラーを返す
        return {
            "message": error_message,
            "status": "error"
        }

# スクレイピング状態を取得するAPI
async def get_scraping_status():
    try:
        # 現在時刻を取得
        now = datetime.now()
        
        # 前回のスクレイピング時刻を datetime に変換
        last_scraping_str = scraping_state.get("last_scraping")
        last_scraping_dt = None
        if last_scraping_str:
            try:
                last_scraping_dt = datetime.strptime(last_scraping_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        
        # 次回のスクレイピング時刻を datetime に変換
        next_scraping_str = scraping_state.get("next_scraping")
        next_scraping_dt = None
        if next_scraping_str:
            try:
                next_scraping_dt = datetime.strptime(next_scraping_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        
        # 経過時間を計算
        time_since_last = "未実行"
        if last_scraping_dt:
            elapsed = now - last_scraping_dt
            hours, remainder = divmod(elapsed.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            time_since_last = f"{int(hours)}時間{int(minutes)}分{int(seconds)}秒"
        
        # 次回ページ範囲
        next_page_range = f"{scraping_state['last_page'] + 1}～{scraping_state['last_page'] + 3}"
        
        return JSONResponse(content={
            "status": "success",
            "data": {
                "is_running": scraping_state["is_running"],
                "last_scraping": scraping_state.get("last_scraping", "未実行"),
                "next_scraping": scraping_state.get("next_scraping", "未定"),
                "time_since_last": time_since_last,
                "auto_scraping_enabled": scraping_state["auto_scraping_enabled"],
                "last_page": scraping_state["last_page"],
                "next_page_range": next_page_range,
                "total_pages_scraped": scraping_state["total_pages_scraped"]
            }
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"スクレイピング状態の取得に失敗しました: {str(e)}"}
        ) 