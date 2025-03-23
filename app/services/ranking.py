"""
JSONファイルからレビューデータを読み込み、サウナランキングを生成するモジュール
GitHub上のJSONファイルを元にランキングを生成します
"""

import re
from collections import defaultdict
from app.services.github_storage import load_recent_reviews

# 穴場キーワードのリスト
HIDDEN_GEM_KEYWORDS = {
    "穴場": 3,
    "隠れた": 2,
    "知る人ぞ知る": 3,
    "秘密": 1,
    "穴場サウナ": 4,
    "隠れ家": 2,
    "穴場スポット": 3,
    "ローカル": 1,
    "ディープ": 1,
    "マイナー": 1,
    "非公開": 2
}

async def generate_sauna_ranking(limit=20, min_reviews=1):
    """
    レビューデータからサウナのランキングを生成
    
    Args:
        limit: 返すランキングの最大数
        min_reviews: ランキングに含めるための最小レビュー数
        
    Returns:
        ランキングのリスト
    """
    try:
        # 最近のレビューを読み込む（上限1000件）
        reviews = load_recent_reviews(limit=1000)
        if not reviews:
            return []
        
        # サウナごとの集計データ
        sauna_data = defaultdict(lambda: {
            "name": "",
            "url": "",
            "review_count": 0,
            "keyword_count": 0,
            "keyword_score": 0,
            "reviews": [],
            "keywords": set()
        })
        
        # レビューデータの集計
        for review in reviews:
            sauna_name = review.get("name", "")
            if not sauna_name:
                continue
                
            # サウナデータの更新
            sauna_data[sauna_name]["name"] = sauna_name
            sauna_data[sauna_name]["url"] = review.get("url", "")
            sauna_data[sauna_name]["review_count"] += 1
            
            # レビューテキストの取得
            review_text = review.get("review", "")
            if not review_text:
                continue
                
            # レビューを保存（最大5件まで）
            if len(sauna_data[sauna_name]["reviews"]) < 5:
                sauna_data[sauna_name]["reviews"].append(review_text)
            
            # キーワードの検索
            for keyword, score in HIDDEN_GEM_KEYWORDS.items():
                if keyword in review_text:
                    sauna_data[sauna_name]["keywords"].add(keyword)
                    sauna_data[sauna_name]["keyword_score"] += score
        
        # ランキングの作成
        ranking = []
        for name, data in sauna_data.items():
            # 最小レビュー数を下回る場合はスキップ
            if data["review_count"] < min_reviews:
                continue
                
            # キーワード数を設定
            data["keyword_count"] = len(data["keywords"])
            
            # キーワードをリストに変換
            data["keywords"] = list(data["keywords"])
            
            # ランキングに追加
            ranking.append(data)
        
        # スコアでソート（レビュー数とキーワードスコアの組み合わせ）
        ranking.sort(key=lambda x: (x["review_count"] * 2 + x["keyword_score"] * 3), reverse=True)
        
        # 上位のみ返す
        return ranking[:limit]
        
    except Exception as e:
        import traceback
        print(f"ランキング生成中にエラー: {e}")
        print(traceback.format_exc())
        return []

async def get_review_count():
    """
    保存されているレビューの総数を取得
    
    Returns:
        レビューの総数
    """
    try:
        reviews = load_recent_reviews(limit=10000)  # 大きな数値を指定して全数をカウント
        return len(reviews)
    except Exception as e:
        print(f"レビュー数取得中にエラー: {e}")
        return 0

async def search_reviews(keyword, limit=50):
    """
    キーワードでレビューを検索
    
    Args:
        keyword: 検索キーワード
        limit: 返す結果の最大数
        
    Returns:
        マッチしたレビューのリスト
    """
    try:
        # キーワードが空の場合は空のリストを返す
        if not keyword:
            return []
            
        # 検索用の正規表現を作成
        pattern = re.compile(keyword, re.IGNORECASE)
        
        # レビューを読み込む
        all_reviews = load_recent_reviews(limit=1000)
        
        # キーワードでフィルタリング
        matched_reviews = []
        for review in all_reviews:
            review_text = review.get("review", "")
            if pattern.search(review_text):
                matched_reviews.append(review)
                if len(matched_reviews) >= limit:
                    break
                    
        return matched_reviews
        
    except Exception as e:
        print(f"レビュー検索中にエラー: {e}")
        return [] 