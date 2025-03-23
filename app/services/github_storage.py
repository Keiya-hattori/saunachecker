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

# 環境変数
IS_RENDER = os.environ.get('RENDER', 'False') == 'True'

# データ保存ディレクトリ
if IS_RENDER:
    # Render環境では一時ディレクトリを使用
    DATA_DIR = Path('/tmp/data')
else:
    # ローカル環境ではプロジェクトディレクトリを使用
    DATA_DIR = Path('data')

SCRAPING_DIR = DATA_DIR / 'scraping'

def ensure_data_dirs():
    """データディレクトリが存在することを確認"""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        SCRAPING_DIR.mkdir(exist_ok=True)
        
        # 年月日のディレクトリ構造を作成
        today = datetime.now().strftime('%Y-%m-%d')
        today_dir = SCRAPING_DIR / today
        today_dir.mkdir(exist_ok=True)
        
        return today_dir
    except Exception as e:
        print(f"データディレクトリの作成エラー: {e}")
        print(traceback.format_exc())
        # エラーが発生しても処理を続行するため、一時的なディレクトリを返す
        if IS_RENDER:
            return Path('/tmp')
        else:
            return Path('.')

def save_reviews_to_json(reviews, batch_name=None):
    """
    スクレイピングしたレビューデータをJSONファイルとして保存
    
    Args:
        reviews: 保存するレビューのリスト
        batch_name: バッチ名（指定されていなければタイムスタンプを使用）
    
    Returns:
        保存したファイルのパス
    """
    try:
        # データディレクトリの確保
        today_dir = ensure_data_dirs()
        
        # ファイル名の生成
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{batch_name}_{timestamp}.json" if batch_name else f"reviews_{timestamp}.json"
        
        # ファイルパスの生成
        file_path = today_dir / filename
        
        # JSONに変換して保存
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(reviews, f, ensure_ascii=False, indent=2)
        
        print(f"レビューデータをJSONに保存しました: {file_path}")
        return file_path
    
    except Exception as e:
        print(f"JSONファイル保存エラー: {e}")
        print(traceback.format_exc())
        
        # Render環境では一時ディレクトリに保存を試みる
        if IS_RENDER:
            try:
                tmp_path = Path('/tmp') / f"temp_reviews_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(reviews, f, ensure_ascii=False, indent=2)
                print(f"一時ディレクトリにレビューデータを保存しました: {tmp_path}")
                return tmp_path
            except Exception as inner_e:
                print(f"一時ディレクトリへの保存も失敗: {inner_e}")
        
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
        limit: 返すレビューの最大数
    
    Returns:
        レビューのリスト
    """
    try:
        # データディレクトリの存在確認
        if not SCRAPING_DIR.exists():
            print(f"スクレイピングディレクトリが存在しません: {SCRAPING_DIR}")
            return []
        
        # 全てのJSONファイルを探す
        all_json_files = []
        
        # 日付ディレクトリ内のJSONファイルを検索
        for date_dir in SCRAPING_DIR.glob('*'):
            if date_dir.is_dir():
                for json_file in date_dir.glob('*.json'):
                    if json_file.is_file() and 'state.json' not in json_file.name:
                        all_json_files.append(json_file)
        
        # ファイルが見つからない場合
        if not all_json_files:
            print("レビューデータのJSONファイルが見つかりません")
            return []
        
        # 最新の更新日時でソート
        all_json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # レビューデータを読み込む
        reviews = []
        
        for file_path in all_json_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_reviews = json.load(f)
                    
                if isinstance(file_reviews, list):
                    reviews.extend(file_reviews)
                    if len(reviews) >= limit:
                        break
            except Exception as e:
                print(f"JSONファイルの読み込みエラー ({file_path}): {e}")
                continue
        
        # 上限数に調整
        return reviews[:limit]
        
    except Exception as e:
        print(f"レビューデータ読み込みエラー: {e}")
        print(traceback.format_exc())
        return []

def get_scraping_state():
    """
    現在のスクレイピング状態を取得
    
    Returns:
        スクレイピング状態の辞書
    """
    try:
        # データディレクトリの確保
        DATA_DIR.mkdir(exist_ok=True)
        
        # 状態ファイルのパス
        state_file = DATA_DIR / 'scraping_state.json'
        
        # ファイルが存在しない場合はデフォルト値を返す
        if not state_file.exists():
            return {
                'last_page': 0,
                'total_pages_scraped': 0,
                'last_run': None,
                'is_running': False,
                'auto_scraping_enabled': False
            }
        
        # 状態ファイルから読み込む
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    except Exception as e:
        print(f"スクレイピング状態の読み込みエラー: {e}")
        print(traceback.format_exc())
        # エラー時はデフォルト値を返す
        return {
            'last_page': 0,
            'total_pages_scraped': 0,
            'last_run': None,
            'is_running': False,
            'auto_scraping_enabled': False
        }

def save_scraping_state(state):
    """
    スクレイピング状態を保存
    
    Args:
        state: 保存する状態の辞書
    
    Returns:
        保存に成功したかどうか
    """
    try:
        # データディレクトリの確保
        try:
            DATA_DIR.mkdir(exist_ok=True)
        except Exception as dir_error:
            print(f"ディレクトリ作成エラー: {dir_error}")
            # Render環境では代替のパスを使用
            if IS_RENDER:
                alt_path = Path('/tmp/scraping_state.json')
                with open(alt_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                print(f"代替パスに状態を保存: {alt_path}")
                return True
            return False
            
        # 状態ファイルのパス
        state_file = DATA_DIR / 'scraping_state.json'
        
        # JSONとして保存
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        
        print(f"スクレイピング状態を保存しました: {state_file}")
        return True
    
    except Exception as e:
        print(f"スクレイピング状態の保存エラー: {e}")
        print(traceback.format_exc())
        
        # Render環境では代替のパスを使用
        if IS_RENDER:
            try:
                alt_path = Path('/tmp/scraping_state.json')
                with open(alt_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                print(f"代替パスに状態を保存: {alt_path}")
                return True
            except Exception as alt_error:
                print(f"代替パスへの保存も失敗: {alt_error}")
        
        return False 