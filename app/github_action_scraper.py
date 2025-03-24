import os
import json
import asyncio
from datetime import datetime, timedelta
import traceback

# サウナスクレイパーと関連モジュールをインポート
from scraper import SaunaScraper
from database import save_reviews

def main():
    """GitHub Actionsから実行されるメイン関数"""
    
    # 永続データディレクトリの設定
    data_dir = "/opt/render/project/src/data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        print(f"Created persistent data directory: {data_dir}")
    
    print(f"GitHub Actions scraper starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # スクレイピング状態を読み込む
        try:
            state_file_path = os.path.join(data_dir, "scraping_state.json")
            if os.path.exists(state_file_path):
                with open(state_file_path, 'r', encoding='utf-8') as f:
                    scraping_state = json.load(f)
                
                # 古いキー名を新しいキー名に変換（互換性のため）
                if "last_page" in scraping_state and "last_scraped_page" not in scraping_state:
                    scraping_state["last_scraped_page"] = scraping_state.pop("last_page")
                    
                if "total_pages_scraped" in scraping_state and "total_scraped_pages" not in scraping_state:
                    scraping_state["total_scraped_pages"] = scraping_state.pop("total_pages_scraped")
                
                print(f"Loaded scraping state: last page = {scraping_state.get('last_scraped_page', 0)}")
            else:
                # 状態ファイルがない場合は初期状態を設定
                scraping_state = {
                    "last_scraped_page": 0,
                    "total_scraped_pages": 0,
                    "is_running": False,
                    "auto_scraping_enabled": True,
                    "last_run": "",
                    "next_scraping": (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
                }
                print("No state file found, starting with initial state")
        except Exception as e:
            print(f"Error loading scraping state: {str(e)}")
            print(traceback.format_exc())
            # エラー時はデフォルト状態を設定
            scraping_state = {
                "last_scraped_page": 0,
                "total_scraped_pages": 0,
                "is_running": False,
                "auto_scraping_enabled": True,
                "last_run": "",
                "next_scraping": (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # 実行中フラグを設定
        scraping_state["is_running"] = True
        save_state(scraping_state, state_file_path)
        
        # スクレイパーを初期化
        scraper = SaunaScraper()
        
        # スクレイピングするページ範囲を決定
        start_page = int(scraping_state.get("last_scraped_page", 0)) + 1
        end_page = start_page + 5  # 1回の実行で5ページをスクレイピング（GitHub Actionsではより多めに処理）
        
        print(f"Scraping pages {start_page} to {end_page}")
        
        # スクレイピングを実行
        results = asyncio.run(scraper.scrape_sauna_reviews(start_page, end_page))
        
        # レビューを保存
        print(f"Scraped {len(results)} reviews")
        saved_count = save_reviews(results)
        print(f"Saved {saved_count} reviews to database")
        
        # 状態を更新
        scraping_state["is_running"] = False
        scraping_state["last_scraped_page"] = end_page
        scraping_state["total_scraped_pages"] += (end_page - start_page + 1)
        scraping_state["last_run"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        scraping_state["next_scraping"] = (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        
        # 状態を保存
        save_state(scraping_state, state_file_path)
        
        print(f"GitHub Actions scraper completed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Next scraping scheduled at {scraping_state['next_scraping']}")
        
    except Exception as e:
        print(f"Error in GitHub Actions scraper: {str(e)}")
        print(traceback.format_exc())
        
        # エラー発生時も状態を更新
        if 'scraping_state' in locals() and 'state_file_path' in locals():
            scraping_state["is_running"] = False
            save_state(scraping_state, state_file_path)
        
        print("GitHub Actions scraper failed")

def save_state(state, filepath):
    """スクレイピング状態を保存する"""
    try:
        # 保存先ディレクトリを確認
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # 状態をJSONファイルとして保存
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        
        print(f"Saved scraping state to {filepath}")
    except Exception as e:
        print(f"Error saving state: {str(e)}")
        print(traceback.format_exc()) 