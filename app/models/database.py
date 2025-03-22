import sqlite3
from datetime import datetime
from pathlib import Path
import traceback

DATABASE_PATH = Path('sauna.db')

def get_db():
    """データベース接続を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # 辞書形式で結果を取得
    return conn

async def init_db(conn=None):
    """データベースの初期化"""
    try:
        if conn is None:
            conn = get_db()
        
        cur = conn.cursor()
        
        # レビューテーブルの作成
        cur.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            review_id TEXT PRIMARY KEY,
            sauna_name TEXT,
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # サウナ統計テーブルの作成
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
        print("データベースを初期化しました")
        print(f"データベースパス: {DATABASE_PATH.absolute()}")
        return True
    except Exception as e:
        print(f"データベース初期化中にエラー発生: {str(e)}")
        print(traceback.format_exc())
        return False
    finally:
        if conn is not None and conn != get_db():
            conn.close()

async def save_review(conn_or_review_id, sauna_name=None, review_text=None, sauna_url=None) -> bool:
    """レビューをデータベースに保存
    
    引数:
        conn_or_review_id: SQLite接続オブジェクトまたはレビューID
        sauna_name: サウナ施設名
        review_text: レビューテキスト
        sauna_url: サウナのURL（オプション）
    """
    conn = None
    review_id = None
    close_conn = False
    
    try:
        # 最初の引数が接続オブジェクトかレビューIDかを判定
        if isinstance(conn_or_review_id, sqlite3.Connection):
            conn = conn_or_review_id
            # URLからレビューIDを生成（URLがない場合は文字列の組み合わせ）
            if sauna_url:
                review_id = sauna_url.replace('https://sauna-ikitai.com', '').replace('/', '_')
            else:
                review_id = f"{sauna_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else:
            # 最初の引数がレビューIDの場合（従来の呼び出し方法）
            conn = get_db()
            close_conn = True
            review_id = conn_or_review_id
        
        print(f"レビュー保存開始: {review_id}")
        
        # データベースが存在しなければ初期化
        if not DATABASE_PATH.exists():
            print("データベースが存在しないため初期化します")
            await init_db(conn)
        
        cur = conn.cursor()
        
        # 重複チェック
        cur.execute("SELECT COUNT(*) FROM reviews WHERE review_id = ?", (review_id,))
        if cur.fetchone()[0] > 0:
            print(f"重複レビュー: {sauna_name} のレビューはすでに存在します")
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
        print(f"レビューを保存しました: {sauna_name}")
        return True
        
    except Exception as e:
        print(f"レビュー保存中にエラー発生: {str(e)}")
        print(traceback.format_exc())
        return False
    finally:
        if close_conn and conn:
            conn.close()

async def get_sauna_ranking(limit: int = 20, conn=None) -> list:
    """サウナのランキングを取得"""
    close_conn = False
    try:
        if not DATABASE_PATH.exists():
            print("データベースが存在しないため初期化します")
            await init_db()
            return []
        
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
        print(f"ランキング取得中にエラー発生: {str(e)}")
        print(traceback.format_exc())
        return []
    finally:
        if close_conn and conn:
            conn.close()

async def get_review_count(conn=None) -> int:
    """保存されているレビューの総数を取得"""
    close_conn = False
    try:
        if not DATABASE_PATH.exists():
            return 0
        
        if conn is None:
            conn = get_db()
            close_conn = True
        
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM reviews")
        count = cur.fetchone()[0]
        
        return count
    except Exception as e:
        print(f"レビュー数取得中にエラー発生: {str(e)}")
        return 0
    finally:
        if close_conn and conn:
            conn.close()

async def get_latest_reviews(limit: int = 10, conn=None) -> list:
    """最新のレビューを取得"""
    close_conn = False
    try:
        if not DATABASE_PATH.exists():
            print("データベースが存在しないため初期化します")
            await init_db()
            return []
        
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
        print(f"最新レビュー取得中にエラー発生: {str(e)}")
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
        print("データベースをリセットしました")
        return True
    except Exception as e:
        print(f"データベースリセット中にエラー発生: {str(e)}")
        print(traceback.format_exc())
        return False
    finally:
        if close_conn and conn:
            conn.close() 