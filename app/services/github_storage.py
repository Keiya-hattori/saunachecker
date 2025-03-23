"""
GitHubリポジトリをストレージとして使用するためのモジュール
スクレイピングしたデータをJSON形式で保存し、GitHub Actionsを通じてコミットします
"""

import json
import os
from datetime import datetime
from pathlib import Path
import subprocess
import traceback

# データ保存ディレクトリ
DATA_DIR = Path('data')
SCRAPING_DIR = DATA_DIR / 'scraping'

def ensure_data_dirs():
    """データディレクトリが存在することを確認"""
    DATA_DIR.mkdir(exist_ok=True)
    SCRAPING_DIR.mkdir(exist_ok=True)
    
    # 年月日のディレクトリ構造を作成
    today = datetime.now().strftime('%Y-%m-%d')
    today_dir = SCRAPING_DIR / today
    today_dir.mkdir(exist_ok=True)
    
    return today_dir

def save_reviews_to_json(reviews, batch_name=None):
    """
    スクレイピングしたレビューデータをJSONファイルとして保存
    
    Args:
        reviews: 保存するレビューデータのリスト
        batch_name: バッチの名前（省略時は現在時刻から自動生成）
    
    Returns:
        保存したファイルのパス
    """
    try:
        # データディレクトリの確認
        today_dir = ensure_data_dirs()
        
        # バッチ名が指定されていない場合は現在時刻から生成
        if not batch_name:
            now = datetime.now().strftime('%H%M%S')
            batch_name = f"batch_{now}"
        
        # ファイル名の作成（例: data/scraping/2023-11-10/batch_123045.json）
        file_path = today_dir / f"{batch_name}.json"
        
        # 保存するデータの作成
        data = {
            "timestamp": datetime.now().isoformat(),
            "count": len(reviews),
            "reviews": reviews
        }
        
        # JSONとして保存
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"レビューデータをJSONに保存しました: {file_path}")
        return str(file_path)
    
    except Exception as e:
        print(f"JSONファイル保存中にエラー: {e}")
        print(traceback.format_exc())
        return None

def commit_and_push_data():
    """
    データディレクトリの変更をGitにコミットしてプッシュ
    GitHub Actionsの環境で実行されることを想定
    
    Returns:
        成功した場合はTrue、失敗した場合はFalse
    """
    try:
        # GitHub Actionsの環境設定
        if 'GITHUB_ACTIONS' in os.environ:
            # Gitの設定
            subprocess.run(['git', 'config', '--global', 'user.name', 'GitHub Actions Bot'])
            subprocess.run(['git', 'config', '--global', 'user.email', 'actions@github.com'])
            
            # 変更をステージング
            subprocess.run(['git', 'add', str(DATA_DIR)])
            
            # 現在時刻を含むコミットメッセージ
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            commit_message = f"データ更新: {now}"
            
            # コミット
            result = subprocess.run(['git', 'commit', '-m', commit_message])
            if result.returncode != 0:
                print("コミットするべき変更がありませんでした")
                return True  # 変更がなくてもエラーとは見なさない
            
            # プッシュ
            subprocess.run(['git', 'push', 'origin', 'master'])
            print(f"データを正常にコミットしてプッシュしました: {commit_message}")
            return True
        else:
            print("GitHub Actions環境ではないため、コミットとプッシュはスキップされました")
            return False
    
    except Exception as e:
        print(f"データのコミットとプッシュ中にエラー: {e}")
        print(traceback.format_exc())
        return False

def load_recent_reviews(limit=100):
    """
    最近のレビューデータをJSONファイルから読み込む
    
    Args:
        limit: 読み込むレビューの最大数
    
    Returns:
        レビューデータのリスト
    """
    try:
        # データディレクトリの確認
        if not SCRAPING_DIR.exists():
            print("スクレイピングデータディレクトリが見つかりません")
            return []
        
        # 日付ディレクトリを新しい順に取得
        date_dirs = sorted([d for d in SCRAPING_DIR.iterdir() if d.is_dir()], reverse=True)
        if not date_dirs:
            print("スクレイピングデータが見つかりません")
            return []
        
        all_reviews = []
        
        # 日付ごとにJSONファイルを読み込む
        for date_dir in date_dirs:
            # その日付のJSONファイルを新しい順に取得
            json_files = sorted([f for f in date_dir.glob('*.json')], key=lambda x: x.stat().st_mtime, reverse=True)
            
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        all_reviews.extend(data.get('reviews', []))
                        
                        # 指定された数に達したら終了
                        if len(all_reviews) >= limit:
                            return all_reviews[:limit]
                except Exception as e:
                    print(f"JSONファイル読み込みエラー {json_file}: {e}")
                    continue
        
        return all_reviews[:limit]
    
    except Exception as e:
        print(f"レビューデータ読み込み中にエラー: {e}")
        print(traceback.format_exc())
        return []

def get_scraping_state():
    """
    スクレイピングの状態を取得
    最後にスクレイピングしたページや日時などの情報を返す
    
    Returns:
        スクレイピング状態の辞書
    """
    state_file = DATA_DIR / 'scraping_state.json'
    
    # デフォルト状態
    default_state = {
        "last_page": 0,
        "total_pages_scraped": 0,
        "last_run": None,
        "is_running": False,
        "auto_scraping_enabled": True
    }
    
    try:
        if state_file.exists():
            with open(state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 状態ファイルがなければデフォルト状態を保存して返す
            save_scraping_state(default_state)
            return default_state
    
    except Exception as e:
        print(f"スクレイピング状態の読み込み中にエラー: {e}")
        print(traceback.format_exc())
        return default_state

def save_scraping_state(state):
    """
    スクレイピングの状態を保存
    
    Args:
        state: 保存する状態の辞書
    
    Returns:
        成功した場合はTrue、失敗した場合はFalse
    """
    try:
        # データディレクトリの確認
        DATA_DIR.mkdir(exist_ok=True)
        state_file = DATA_DIR / 'scraping_state.json'
        
        # JSONとして保存
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        
        print(f"スクレイピング状態を保存しました: 最終ページ {state.get('last_page', 0)}")
        return True
    
    except Exception as e:
        print(f"スクレイピング状態の保存中にエラー: {e}")
        print(traceback.format_exc())
        return False 