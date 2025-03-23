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

def get_db_session():
    """データベース接続を取得（get_dbのエイリアス）"""
    return get_db()

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
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            crowdedness_status TEXT DEFAULT NULL
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

# DBモデルの定義
class Review:
    """レビューモデル"""
    def __init__(self, review_id, sauna_name, review_text, created_at=None):
        self.review_id = review_id
        self.sauna_name = sauna_name
        self.review_text = review_text
        self.created_at = created_at or datetime.now()

class SaunaStats:
    """サウナ統計モデル"""
    def __init__(self, sauna_id, sauna_name, review_count=0, score=0, last_updated=None, crowdedness_status=None):
        self.sauna_id = sauna_id
        self.sauna_name = sauna_name
        self.review_count = review_count
        self.score = score
        self.last_updated = last_updated or datetime.now()
        self.crowdedness_status = crowdedness_status
        
    def save(self):
        """サウナ統計を保存（更新）"""
        try:
            conn = get_db()
            cur = conn.cursor()
            
            # 既存のレコードを更新
            cur.execute('''
                UPDATE sauna_stats 
                SET review_count = ?, score = ?, last_updated = ?, crowdedness_status = ?
                WHERE sauna_id = ?
            ''', (
                self.review_count, 
                self.score, 
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                self.crowdedness_status,
                self.sauna_id
            ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"サウナ統計更新中にエラー: {str(e)}")
            return False
        finally:
            if conn:
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
    """サウナランキングを取得"""
    close_conn = False
    try:
        if conn is None:
            conn = get_db()
            close_conn = True
        
        cur = conn.cursor()
        
        # レビュー数が多い順にサウナをランキング
        cur.execute('''
            SELECT 
                sauna_id, 
                sauna_name, 
                review_count, 
                score,
                last_updated,
                crowdedness_status
            FROM sauna_stats 
            ORDER BY review_count DESC, score DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cur.fetchall()
        
        # 辞書のリストに変換
        result = []
        for row in rows:
            result.append({
                'sauna_id': row['sauna_id'],
                'name': row['sauna_name'],
                'review_count': row['review_count'],
                'score': row['score'],
                'last_updated': row['last_updated'],
                'crowdedness_status': row['crowdedness_status']
            })
        
        return result
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

async def get_sauna_stats_by_name(sauna_name, conn=None) -> SaunaStats:
    """サウナ名から統計情報を取得"""
    close_conn = False
    try:
        if conn is None:
            conn = get_db()
            close_conn = True
        
        cur = conn.cursor()
        
        # サウナ名で検索
        cur.execute('''
            SELECT * FROM sauna_stats WHERE sauna_name = ?
        ''', (sauna_name,))
        
        row = cur.fetchone()
        
        if row:
            # サウナ統計オブジェクトを作成して返す
            try:
                # 存在するか確認して値を取得しようとする
                crowdedness_status = row['crowdedness_status']
            except (KeyError, IndexError):
                # キーが存在しない場合はNoneを設定
                crowdedness_status = None
                
            return SaunaStats(
                sauna_id=row['sauna_id'],
                sauna_name=row['sauna_name'],
                review_count=row['review_count'],
                score=row['score'],
                last_updated=row['last_updated'],
                crowdedness_status=crowdedness_status
            )
        return None
    except Exception as e:
        print(f"サウナ統計取得中にエラー: {str(e)}")
        print(traceback.format_exc())
        return None
    finally:
        if close_conn and conn:
            conn.close() 