from fastapi import APIRouter
from app.services.scraper import SaunaScraper
from app.config import HIDDEN_GEM_KEYWORDS
from app.models.database import get_sauna_ranking, get_review_count

router = APIRouter()
scraper = SaunaScraper()

@router.get("/api/test/scraping")
async def test_scraping():
    """ローカルファイルを使用したスクレイピングテスト"""
    try:
        reviews = await scraper.get_hidden_gem_reviews_test()
        print(f"取得したレビュー数: {len(reviews)}")
        
        # サウナごとの穴場カウントを集計
        sauna_counts = {}
        for review in reviews:
            sauna_name = review["name"]
            if sauna_name not in sauna_counts:
                sauna_counts[sauna_name] = {
                    "count": 0,
                    "url": review["url"],
                    "reviews": [],
                    "keywords": set()
                }
            sauna_counts[sauna_name]["count"] += 1
            sauna_counts[sauna_name]["reviews"].append(review["review"])
            
            # レビュー内のキーワードを抽出
            for keyword in HIDDEN_GEM_KEYWORDS.keys():
                if keyword in review["review"]:
                    sauna_counts[sauna_name]["keywords"].add(keyword)
        
        # ランキング形式でソート
        ranking = []
        for name, data in sauna_counts.items():
            keywords_list = list(data["keywords"])
            ranking.append({
                "name": name,
                "url": data["url"],
                "review_count": data["count"],
                "keywords": keywords_list,
                "keyword_count": len(keywords_list),
                "reviews": data["reviews"][:3]  # 最新3件のみを表示
            })
        
        # レビュー数とキーワード数で降順ソート
        ranking.sort(key=lambda x: (x["review_count"], x["keyword_count"]), reverse=True)
        
        return {
            "status": "success",
            "message": f"{len(reviews)}件のテストレビューを取得しました",
            "total_saunas": len(ranking),
            "ranking": ranking
        }
    except Exception as e:
        print(f"ランキング処理中にエラー発生: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@router.get("/api/ranking")
async def get_ranking(limit: int = 40):
    """データベースに基づいたサウナランキングを取得"""
    try:
        # データベースからランキングを取得
        ranking = await get_sauna_ranking(limit)
        total_reviews = await get_review_count()
        
        return {
            "status": "success",
            "message": f"データベースから{len(ranking)}件のサウナランキングを取得しました",
            "total_reviews": total_reviews,
            "total_saunas": len(ranking),
            "ranking": ranking
        }
    except Exception as e:
        print(f"ランキング取得中にエラー発生: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        } 