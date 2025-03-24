import os
import sqlite3
import json
from pathlib import Path
import traceback
from datetime import datetime
from app.models.database import get_db, save_review, init_db

# 環境変数
IS_RENDER = os.environ.get('RENDER', 'False') == 'True'

# データディレクトリの設定
if IS_RENDER:
    DATA_DIR = Path('/opt/render/project/src/data')
else:
    DATA_DIR = Path('./data')

# データベースのパス
DB_PATH = DATA_DIR / 'sauna_app.db'

# 初期化フラグ
SAVE_INFO_SHOWN = False

async def save_reviews(reviews):
    """複数のレビューをデータベースに保存する"""
    global SAVE_INFO_SHOWN
    
    if not reviews:
        return 0
        
    saved_count = 0
    
    # データベース接続を取得
    db = get_db()
    
    try:
        # 一度だけ情報を表示
        if not SAVE_INFO_SHOWN:
            print(f"レビュー保存処理開始: {len(reviews)}件")
            SAVE_INFO_SHOWN = True
            
        # 各レビューを保存
        for review in reviews:
            try:
                # レビューがあるかチェック
                review_id = review.get('review_id')
                sauna_name = review.get('sauna_name')
                review_text = review.get('review_text')
                
                if not (review_id and sauna_name and review_text):
                    continue
                    
                # レビューを保存
                success = save_review(
                    db, 
                    review_id, 
                    sauna_name, 
                    review_text
                )
                
                if success:
                    saved_count += 1
                    
            except Exception as e:
                print(f"レビュー個別保存エラー: {str(e)}")
        
        return saved_count
        
    except Exception as e:
        print(f"レビュー一括保存エラー: {str(e)}")
        return saved_count
        
    finally:
        if saved_count > 0:
            print(f"レビュー保存完了: {saved_count}/{len(reviews)}件")

async def update_ratings(url, rating_data=None):
    """サウナ施設の評価データを更新する"""
    try:
        # 単一URLの場合
        if rating_data is not None:
            # URLからサウナIDを抽出
            sauna_id = url.split("/")[-1]
            if not sauna_id.isdigit():
                return {"success": False, "message": "無効なURL形式です"}
                
            # データベース接続
            db = get_db()
            
            # 現在の日時
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # JSON形式に変換
            rating_json = json.dumps(rating_data, ensure_ascii=False)
            
            # データを挿入または更新
            cursor = db.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO sauna_stats 
                (sauna_id, rating_data, updated_at) 
                VALUES (?, ?, ?)
            ''', (sauna_id, rating_json, now))
            
            db.commit()
            
            return {
                "success": True, 
                "message": "評価データを保存しました", 
                "sauna_id": sauna_id
            }
        # 複数の評価データの場合（互換性のため残す）
        else:
            ratings_data = url  # この場合、最初の引数がratings_dataになる
            
            if not ratings_data:
                return {"success": False, "message": "評価データがありません"}
                
            # データベース接続
            db = get_db()
            
            # 現在の日時
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for sauna_id, rating in ratings_data.items():
                try:
                    # JSON形式に変換
                    rating_json = json.dumps(rating, ensure_ascii=False)
                    
                    # データを挿入または更新
                    cursor = db.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO sauna_stats 
                        (sauna_id, rating_data, updated_at) 
                        VALUES (?, ?, ?)
                    ''', (sauna_id, rating_json, now))
                except Exception as e:
                    print(f"サウナID {sauna_id} の評価更新エラー: {str(e)}")
            
            db.commit()
            
            return {
                "success": True, 
                "message": f"{len(ratings_data)}件の評価データを保存しました"
            }
            
    except Exception as e:
        print(f"評価データ更新エラー: {str(e)}")
        print(traceback.format_exc())
        
        return {
            "success": False, 
            "message": f"評価データの保存に失敗しました: {str(e)}"
        }

async def update_ratings(ratings_data):
    """サウナの評価を更新

    Args:
        ratings_data (dict): 評価データ

    Returns:
        bool: 更新が成功したかどうか
    """
    if not ratings_data:
        return False
    
    conn = get_db()
    try:
        cur = conn.cursor()
        
        for sauna_id, rating in ratings_data.items():
            # サウナの評価を更新
            cur.execute(
                "UPDATE sauna_stats SET rating = ? WHERE sauna_id = ?",
                (rating, sauna_id)
            )
        
        conn.commit()
        return True
    
    except Exception as e:
        print(f"評価更新中にエラー発生: {str(e)}")
        return False
    finally:
        conn.close() 