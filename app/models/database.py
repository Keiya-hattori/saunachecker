import sqlite3
from datetime import datetime
from pathlib import Path
import traceback
import os
import sys

# 環境情報は起動時に1度だけ表示
IS_RENDER = os.environ.get('RENDER', 'False') == 'True'
ENV_INFO_DISPLAYED = False

# データベースディレクトリの設定
if IS_RENDER:
    # Render環境では永続的なデータディレクトリを使用
    DATA_DIR = Path('/opt/render/project/src/data')
    # ディレクトリが存在しない場合は作成
    DATA_DIR.mkdir(exist_ok=True)
    
    DATABASE_PATH = DATA_DIR / 'sauna_temp.db'
else:
    # ローカル環境ではプロジェクトディレクトリにデータベースを保存
    DATABASE_PATH = Path('sauna_temp.db')

def display_env_info_once():
    """環境情報を1度だけ表示する"""
    global ENV_INFO_DISPLAYED
    if not ENV_INFO_DISPLAYED:
        if IS_RENDER:
            print(f"環境: Render (データベース: {DATABASE_PATH})")
        else:
            print(f"環境: ローカル (データベース: {DATABASE_PATH})")
        ENV_INFO_DISPLAYED = True

def get_db():
    """データベース接続を取得"""
    try:
        # 環境情報を表示
        display_env_info_once()
        
        # データベースディレクトリが存在することを確認
        DATABASE_PATH.parent.mkdir(exist_ok=True)
        
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row  # 辞書形式で結果を取得
        return conn
    except Exception as e:
        print(f"データベース接続エラー: {e}")
        print(traceback.format_exc())
        # エラーを再発生させる
        raise

# テーブル初期化の状態を記録
DB_INITIALIZED = False

async def init_db(conn=None):
    """データベースの初期化"""
    global DB_INITIALIZED
    
    # 既に初期化済みの場合はスキップ
    if DB_INITIALIZED:
        return True
    
    try:
        if conn is None:
            conn = get_db()
        
        cur = conn.cursor()
        
        # テーブルの作成
        cur.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            review_id TEXT PRIMARY KEY,
            sauna_name TEXT,
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS sauna_stats (
            sauna_id TEXT PRIMARY KEY,
            sauna_name TEXT,
            review_count INTEGER DEFAULT 0,
            score REAL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        
        # テーブルが作成されたか確認
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'")
        has_reviews_table = cur.fetchone() is not None
        
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sauna_stats'")
        has_stats_table = cur.fetchone() is not None
        
        if has_reviews_table and has_stats_table:
            print(f"データベーステーブル初期化完了 (reviews, sauna_stats)")
            DB_INITIALIZED = True
            return True
        else:
            print(f"警告: テーブル初期化に問題があります (reviews: {has_reviews_table}, sauna_stats: {has_stats_table})")
            return False
            
    except Exception as e:
        print(f"データベース初期化エラー: {str(e)}")
        print(traceback.format_exc())
        return False
    finally:
        if conn is not None and conn != get_db():
            conn.close()

async def save_review(conn_or_review_id, sauna_name=None, review_text=None, sauna_url=None) -> bool:
    """レビューをデータベースに保存"""
    conn = None
    review_id = None
    close_conn = False
    
    try:
        # 最初の引数が接続オブジェクトかレビューIDかを判定
        if isinstance(conn_or_review_id, sqlite3.Connection):
            conn = conn_or_review_id
            # URLからレビューIDを生成
            if sauna_url:
                review_id = sauna_url.replace('https://sauna-ikitai.com', '').replace('/', '_')
            else:
                review_id = f"{sauna_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else:
            # 最初の引数がレビューIDの場合
            conn = get_db()
            close_conn = True
            review_id = conn_or_review_id
        
        # データベーステーブルを初期化
        await init_db(conn)
        
        cur = conn.cursor()
        
        # 重複チェック（短いログメッセージ）
        cur.execute("SELECT COUNT(*) FROM reviews WHERE review_id = ?", (review_id,))
        if cur.fetchone()[0] > 0:
            return False
        
        # 新しいレビューを挿入
        cur.execute(
            "INSERT INTO reviews (review_id, sauna_name, review_text) VALUES (?, ?, ?)",
            (review_id, sauna_name, review_text)
        )
        
        # サウナ統計の更新（存在しない場合は作成）
        sauna_id = sauna_name.replace(" ", "_").lower()
        
        cur.execute("SELECT review_count FROM sauna_stats WHERE sauna_id = ?", (sauna_id,))
        result = cur.fetchone()
        
        if result:
            # 既存のサウナ統計を更新
            cur.execute(
                "UPDATE sauna_stats SET review_count = review_count + 1, last_updated = CURRENT_TIMESTAMP WHERE sauna_id = ?",
                (sauna_id,)
            )
        else:
            # 新しいサウナ統計を作成
            cur.execute(
                "INSERT INTO sauna_stats (sauna_id, sauna_name, review_count) VALUES (?, ?, 1)",
                (sauna_id, sauna_name)
            )
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"レビュー保存エラー ({review_id}): {str(e)}")
        print(traceback.format_exc())
        return False
    finally:
        if close_conn and conn:
            conn.close()

async def get_sauna_ranking(limit: int = 20, conn=None) -> list:
    """サウナのランキングを取得"""
    close_conn = False
    try:
        # データベーステーブルを初期化
        await init_db()
        
        if conn is None:
            conn = get_db()
            close_conn = True
        
        cur = conn.cursor()
        
        # レビュー数の多い順にサウナを取得
        cur.execute("""
        SELECT sauna_id, sauna_name, review_count, last_updated
        FROM sauna_stats
        ORDER BY review_count DESC, last_updated DESC
        LIMIT ?
        """, (limit,))
        
        results = []
        for row in cur.fetchall():
            results.append({
                "sauna_id": row["sauna_id"],
                "name": row["sauna_name"],
                "review_count": row["review_count"],
                "last_updated": row["last_updated"]
            })
        
        return results
    except Exception as e:
        print(f"ランキング取得エラー: {str(e)}")
        print(traceback.format_exc())
        return []
    finally:
        if close_conn and conn:
            conn.close()

async def get_review_count(conn=None) -> int:
    """保存されているレビューの総数を取得"""
    close_conn = False
    try:
        # データベーステーブルを初期化
        await init_db()
        
        if conn is None:
            conn = get_db()
            close_conn = True
        
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM reviews")
        count = cur.fetchone()[0]
        
        return count
    except Exception as e:
        print(f"レビュー数取得エラー: {str(e)}")
        return 0
    finally:
        if close_conn and conn:
            conn.close()

async def get_latest_reviews(limit: int = 10, conn=None) -> list:
    """最新のレビューを取得"""
    close_conn = False
    try:
        # データベーステーブルを初期化
        await init_db()
        
        if conn is None:
            conn = get_db()
            close_conn = True
        
        cur = conn.cursor()
        
        # 最新のレビューを取得
        cur.execute("""
        SELECT review_id, sauna_name, review_text, created_at
        FROM reviews
        ORDER BY created_at DESC
        LIMIT ?
        """, (limit,))
        
        results = []
        for row in cur.fetchall():
            results.append({
                "review_id": row["review_id"],
                "sauna_name": row["sauna_name"],
                "review_text": row["review_text"],
                "created_at": row["created_at"]
            })
        
        return results
    except Exception as e:
        print(f"最新レビュー取得エラー: {str(e)}")
        print(traceback.format_exc())
        return []
    finally:
        if close_conn and conn:
            conn.close()

async def reset_database(conn=None):
    """データベースをリセットする"""
    close_conn = False
    try:
        if conn is None:
            conn = get_db()
            close_conn = True
        
        cur = conn.cursor()
        
        # レビューテーブルを空にする
        cur.execute("DELETE FROM reviews")
        
        # サウナ統計テーブルを空にする
        cur.execute("DELETE FROM sauna_stats")
        
        conn.commit()
        print("データベースリセット完了")
        return True
    except Exception as e:
        print(f"データベースリセットエラー: {str(e)}")
        print(traceback.format_exc())
        return False
    finally:
        if close_conn and conn:
            conn.close() 