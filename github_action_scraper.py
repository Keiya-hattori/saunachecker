#!/usr/bin/env python3
"""
GitHub Actionsで実行されるスクレイピングスクリプト
サウナレビューをスクレイピングし、JSONファイルとして保存します
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# スクリプトのディレクトリを追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from app.services.scraper import SaunaScraper
from app.services.github_storage import save_reviews_to_json, get_scraping_state, save_scraping_state

async def main():
    """メイン関数: スクレイピングを実行し、JSONとして保存します"""
    print("サウナレビュースクレイピングを開始します")
    start_time = datetime.now()
    
    try:
        # スクレイピング状態を取得
        state = get_scraping_state()
        
        # スクレイピングの開始ページと終了ページを決定
        start_page = state.get('last_page', 0) + 1
        end_page = start_page + 2  # 3ページずつスクレイピング
        
        if start_page <= 0:
            start_page = 1
            end_page = 3
        
        print(f"ページ範囲 {start_page}〜{end_page} をスクレイピングします")
        
        # スクレイピング実行中フラグを設定
        state['is_running'] = True
        save_scraping_state(state)
        
        # スクレイパーを初期化
        scraper = SaunaScraper()
        
        # スクレイピングを実行
        reviews = await scraper.get_hidden_gem_reviews(
            max_pages=3,
            start_page=start_page,
            end_page=end_page
        )
        
        # スクレイピング完了時間
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"スクレイピング完了: {len(reviews)}件のレビューを取得しました (処理時間: {duration:.2f}秒)")
        
        # スクレイピング結果をJSONとして保存
        batch_name = f"pages_{start_page}_to_{end_page}"
        saved_path = save_reviews_to_json(reviews, batch_name)
        
        if saved_path:
            print(f"データを保存しました: {saved_path}")
        
        # 状態を更新
        state['last_page'] = end_page
        state['last_run'] = datetime.now().isoformat()
        state['total_pages_scraped'] = state.get('total_pages_scraped', 0) + (end_page - start_page + 1)
        state['is_running'] = False
        save_scraping_state(state)
        
        print(f"スクレイピング状態を更新しました: 最終ページ={end_page}, 次回のページ範囲={end_page+1}〜{end_page+3}")
        
        # 合計レビュー数を計算
        total_reviews = len(reviews)
        print(f"今回のバッチで {total_reviews} 件のレビューを取得しました")
        
        return {
            "status": "success",
            "batch": batch_name,
            "page_range": f"{start_page}〜{end_page}",
            "next_page_range": f"{end_page+1}〜{end_page+3}",
            "review_count": total_reviews,
            "processing_time": f"{duration:.2f}秒"
        }
        
    except Exception as e:
        import traceback
        print(f"スクレイピング中にエラーが発生しました: {e}")
        print(traceback.format_exc())
        
        # エラー発生時も状態を更新
        try:
            state = get_scraping_state()
            state['is_running'] = False
            save_scraping_state(state)
        except:
            pass
        
        return {
            "status": "error",
            "error": str(e)
        }

if __name__ == "__main__":
    # 非同期関数を実行
    result = asyncio.run(main())
    
    # 終了コードを設定（成功: 0, 失敗: 1）
    sys.exit(0 if result.get("status") == "success" else 1) 