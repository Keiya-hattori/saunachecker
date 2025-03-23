import asyncio
import time
from datetime import datetime, timedelta
import traceback
import json
import os
from pathlib import Path
from app.services.scraper import SaunaScraper
from app.models.database import get_sauna_ranking, get_review_count, get_db, save_review, init_db

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
    # Render環境では/data/ディレクトリに状態ファイルを保存
    DATA_DIR = Path('/data')
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(exist_ok=True)
    SCRAPING_STATE_FILE = DATA_DIR / 'scraping_state.json'
else:
    # ローカル環境ではプロジェクトディレクトリに状態ファイルを保存
    SCRAPING_STATE_FILE = Path('scraping_state.json')

# 初期状態
scraping_state = {
    "last_page": 0,
    "last_run": None,
    "total_pages_scraped": 0,
    "is_running": False,
    "auto_scraping_enabled": False
}

def load_scraping_state():
    """スクレイピング状態をファイルから読み込む"""
    global scraping_state
    try:
        if SCRAPING_STATE_FILE.exists():
            print(f"スクレイピング状態ファイルをロード中: {SCRAPING_STATE_FILE}")
            with open(SCRAPING_STATE_FILE, 'r', encoding='utf-8') as f:
                loaded_state = json.load(f)
                # 必要なキーが全て含まれているか確認
                required_keys = ["last_page", "total_pages_scraped", "auto_scraping_enabled"]
                if all(key in loaded_state for key in required_keys):
                    # 実行中状態はリセット
                    loaded_state["is_running"] = False
                    # 時刻関連の情報は現在の状態を維持
                    loaded_state["last_scraping"] = scraping_state.get("last_scraping")
                    loaded_state["next_scraping"] = scraping_state.get("next_scraping")
                    scraping_state.update(loaded_state)
                    print(f"スクレイピング状態を読み込みました: 最終ページ {scraping_state['last_page']}")
                else:
                    print("状態ファイルのフォーマットが不正です。デフォルト値を使用します。")
                    # 初期状態を保存
                    save_scraping_state()
        else:
            print(f"スクレイピング状態ファイルが見つかりません: {SCRAPING_STATE_FILE}")
            print("初期状態を使用します。")
            save_scraping_state()
    except Exception as e:
        print(f"状態ファイルの読み込みエラー: {e}")
        print(traceback.format_exc())
        print("エラーにより初期状態を使用します。")
        save_scraping_state()

def save_scraping_state():
    """スクレイピング状態をファイルに保存する"""
    try:
        # Render環境では/dataディレクトリを確認
        if IS_RENDER:
            if not DATA_DIR.exists():
                DATA_DIR.mkdir(exist_ok=True)
                print(f"Render環境で/dataディレクトリを作成しました")
        
        # ディレクトリが確実に存在することを確認
        SCRAPING_STATE_FILE.parent.mkdir(exist_ok=True)
        
        with open(SCRAPING_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(scraping_state, f, ensure_ascii=False, indent=2)
        print(f"スクレイピング状態を保存しました: 最終ページ {scraping_state['last_page']}")
        print(f"保存先: {SCRAPING_STATE_FILE}")
    except Exception as e:
        print(f"状態ファイルの保存エラー: {e}")
        print(traceback.format_exc())

async def periodic_scraping():
    """30分ごとに自動的にスクレイピングを実行するバックグラウンドタスク"""
    global last_scraping_time, scraping_state
    
    # 起動時にスクレイピング状態を読み込む
    load_scraping_state()
    
    print(f"バックグラウンドスクレイピングタスクを開始しました。30分ごとに実行します。")
    print(f"自動スクレイピング有効: {scraping_state['auto_scraping_enabled']}")
    
    # 自動スクレイピングが無効になっている場合は待機するだけ
    if not scraping_state['auto_scraping_enabled']:
        print("自動スクレイピングは無効になっています。手動で有効化するまで待機します。")
        while not scraping_state['auto_scraping_enabled']:
            await asyncio.sleep(60)  # 1分ごとに設定を確認
        
    while True:
        try:
            # 自動スクレイピングが無効になっていたら待機
            if not scraping_state['auto_scraping_enabled']:
                print("自動スクレイピングは無効になっています。手動で有効化するまで待機します。")
                while not scraping_state['auto_scraping_enabled']:
                    await asyncio.sleep(60)  # 1分ごとに設定を確認
                continue

            # 現在時刻を取得
            now = datetime.now()
            
            # スクレイピングの実行
            print(f"自動スクレイピング開始: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 今回スクレイピングするページ範囲を決定
            start_page = scraping_state['last_page'] + 1
            end_page = start_page + 2  # 3ページずつスクレイピング
            
            # ページ範囲が1から始まるようにする
            if start_page <= 0:
                start_page = 1
                end_page = 3
            
            print(f"スクレイピング範囲: {start_page}〜{end_page}ページ")
            
            # ページ範囲を指定して実サイトからのスクレイピングを実行
            scraping_state['is_running'] = True
            save_scraping_state()
            
            reviews = await scraper.get_hidden_gem_reviews(
                max_pages=3,
                start_page=start_page,
                end_page=end_page
            )
            
            # スクレイピング状態を更新
            scraping_state['last_page'] = end_page
            scraping_state['last_run'] = now.strftime('%Y-%m-%d %H:%M:%S')
            scraping_state['total_pages_scraped'] += (end_page - start_page + 1)
            scraping_state['is_running'] = False
            save_scraping_state()
            
            # 結果の取得と記録
            ranking = await get_sauna_ranking(limit=20)
            total_reviews = await get_review_count()
            
            # 前回からの新規レビュー数を計算
            new_reviews_count = len(reviews)
            
            # 最終スクレイピング時刻を更新
            last_scraping_time = now
            
            print(f"自動スクレイピング完了: {new_reviews_count}件のレビューを取得しました")
            print(f"ランキング更新: 総レビュー数 {total_reviews}件、総サウナ数 {len(ranking)}件")
            print(f"次回のスクレイピングは15分後です（{start_page + 3}〜{end_page + 3}ページ）")
            
            # 15分間待機
            await asyncio.sleep(15 * 60)  # 15分 = 900秒
            
        except Exception as e:
            print(f"自動スクレイピング中にエラー発生: {str(e)}")
            print(traceback.format_exc())
            
            # エラー発生時にスクレイピング状態を更新
            scraping_state['is_running'] = False
            save_scraping_state()
            
            # エラー時は5分後に再試行
            print(f"5分後に再試行します")
            await asyncio.sleep(5 * 60)  # 5分 = 300秒

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

async def toggle_auto_scraping(enable=None):
    """自動スクレイピングの有効/無効を切り替える"""
    global scraping_state
    
    # 現在のスクレイピング状態を読み込む
    load_scraping_state()
    
    if enable is not None:
        scraping_state["auto_scraping_enabled"] = enable
    else:
        # 指定がなければ現在の状態を反転
        scraping_state["auto_scraping_enabled"] = not scraping_state["auto_scraping_enabled"]
    
    save_scraping_state()
    
    return {
        "auto_scraping_enabled": scraping_state["auto_scraping_enabled"],
        "message": f"自動スクレイピングを{'有効' if scraping_state['auto_scraping_enabled'] else '無効'}にしました"
    }

async def reset_scraping_state():
    """スクレイピング状態をリセットする"""
    global scraping_state
    
    scraping_state = {
        "last_page": 0,
        "last_run": None,
        "total_pages_scraped": 0,
        "is_running": False,
        "auto_scraping_enabled": False
    }
    
    save_scraping_state()
    
    return {
        "message": "スクレイピング状態をリセットしました",
        "state": scraping_state
    }

# 起動時に状態を読み込む
load_scraping_state()

# 周期的なスクレイピングタスクを開始する背景タスク
async def start_periodic_scraping():
    # 自動スクレイピングが無効の場合は何もしない
    if not scraping_state["auto_scraping_enabled"]:
        print("自動スクレイピングは無効化されています。")
        return

    # 初回実行は即時
    asyncio.create_task(periodic_scraping())
    
    # 30分ごとに実行するループ
    while True:
        # 次回実行時刻を30分後に設定
        now = datetime.now()
        next_run = now + timedelta(minutes=30)
        scraping_state["next_scraping"] = next_run.strftime("%Y-%m-%d %H:%M:%S")
        
        # 30分待機
        print(f"次回スクレイピングは {scraping_state['next_scraping']} に実行予定です")
        await asyncio.sleep(30 * 60)  # 30分 = 1800秒
        
        # 自動スクレイピングが無効になっていたら終了
        if not scraping_state["auto_scraping_enabled"]:
            print("自動スクレイピングが無効化されたため、定期実行を停止します。")
            break
            
        # スクレイピング実行
        asyncio.create_task(periodic_scraping())

# 実際のスクレイピングを行う関数
async def periodic_scraping():
    global scraping_state
    
    if scraping_state["is_running"]:
        print("スクレイピングは既に実行中です")
        return
    
    try:
        scraping_state["is_running"] = True
        print("定期的なスクレイピングを開始します...")
        
        # 現在の時刻を記録
        now = datetime.now()
        scraping_state["last_scraping"] = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # スクレイピングの開始ページと終了ページを決定
        start_page = scraping_state["last_page"] + 1
        end_page = start_page + 2  # 3ページずつスクレイピング
        
        print(f"{start_page}ページから{end_page}ページまでスクレイピングします...")
        
        # スクレイピング実行
        scraper = SaunaScraper()
        reviews = await scraper.get_hidden_gem_reviews(start_page=start_page, end_page=end_page)
        
        # DB初期化（必要であれば）
        db_conn = get_db()
        init_db(db_conn)
        
        # レビューを保存
        review_count = 0
        for review in reviews:
            success = save_review(
                db_conn,
                review["sauna_name"],
                review["review_text"],
                review["sauna_url"]
            )
            if success:
                review_count += 1
        
        print(f"{review_count}件のレビューを保存しました")
        
        # 状態を更新
        scraping_state["last_page"] = end_page
        scraping_state["total_pages_scraped"] += (end_page - start_page + 1)
        
        # 状態を保存
        save_scraping_state()
        
    except Exception as e:
        print(f"スクレイピング中にエラーが発生しました: {e}")
    finally:
        scraping_state["is_running"] = False

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

# 自動スクレイピングの有効/無効を切り替えるAPI
async def toggle_auto_scraping(enable: bool, background_tasks: BackgroundTasks):
    global scraping_state
    
    try:
        # 状態を更新
        scraping_state["auto_scraping_enabled"] = enable
        
        # 状態をファイルに保存
        save_scraping_state()
        
        # 有効化された場合、バックグラウンドタスクを開始
        if enable and not any(task.get_name() == "periodic_scraping" for task in asyncio.all_tasks()):
            background_tasks.add_task(start_periodic_scraping)
            message = "自動スクレイピングを有効化しました。30分ごとに実行されます。"
        else:
            message = "自動スクレイピングを無効化しました。"
        
        return JSONResponse(content={
            "status": "success",
            "data": {
                "enabled": enable,
                "message": message
            }
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"設定の変更に失敗しました: {str(e)}"}
        )

# スクレイピング状態をリセットするAPI
async def reset_scraping_state():
    global scraping_state
    
    try:
        # 状態をリセット
        scraping_state["last_page"] = 0
        scraping_state["total_pages_scraped"] = 0
        
        # 状態をファイルに保存
        save_scraping_state()
        
        return JSONResponse(content={
            "status": "success",
            "data": {
                "message": "スクレイピング状態をリセットしました。次回は1ページ目から開始されます。"
            }
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"状態のリセットに失敗しました: {str(e)}"}
        ) 