import asyncio
from app.models.database import get_db, save_review, init_db

async def save_reviews(reviews):
    """複数のレビューをデータベースに保存

    Args:
        reviews (list): レビューのリスト

    Returns:
        int: 保存されたレビューの数
    """
    if not reviews:
        return 0
    
    # データベース接続を取得
    conn = get_db()
    saved_count = 0
    
    try:
        for review in reviews:
            # 各レビューをデータベースに保存
            sauna_name = review.get('sauna_name', '')
            review_text = review.get('review_text', '')
            sauna_url = review.get('url', None)
            
            # save_review関数を使用
            success = await save_review(conn, sauna_name, review_text, sauna_url)
            if success:
                saved_count += 1
        
        return saved_count
    
    except Exception as e:
        print(f"レビュー保存中にエラー発生: {str(e)}")
        return saved_count
    finally:
        # 接続を閉じる
        conn.close()

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