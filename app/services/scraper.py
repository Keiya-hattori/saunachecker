from bs4 import BeautifulSoup
import re
from pathlib import Path
from app.config import TEST_HTML_PATHS, HIDDEN_GEM_KEYWORDS
import aiohttp
import asyncio
import traceback
import time
import uuid
import json

# ログ抑制フラグ
VERBOSE_LOGGING = False

class SaunaScraper:
    def __init__(self):
        self.base_url = "https://sauna-ikitai.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "DNT": "1",
            "Referer": "https://sauna-ikitai.com/"
        }
        # 隠れた名店に関連するキーワード
        self.hidden_gem_keywords = ["穴場", "隠れた", "静か", "空いている", "人が少ない", "混雑していない", "穴スポ"]

    async def analyze_sauna(self, url: str) -> dict:
        """特定のサウナの穴場評価を行う（URL指定 - 機能2）"""
        try:
            if not url.startswith("https://sauna-ikitai.com/saunas/"):
                return {"error": "URLがサウナイキタイの施設ページではありません"}
                
            # URLからサウナ情報とレビューを取得
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status != 200:
                        return {"error": f"ページの取得に失敗しました (ステータスコード: {response.status})"}
                    
                    html = await response.text()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # サウナ名を取得
            sauna_name_element = soup.select_one('h1.p-saunaDetailHeader_title')
            sauna_name = sauna_name_element.text.strip() if sauna_name_element else "不明なサウナ施設"
            
            # レビューテキストを取得
            reviews = soup.select('div.p-postCard_body p.p-postCard_text')
            all_review_texts = []
            
            for review in reviews:
                # 改行を適切に処理
                for br in review.find_all('br'):
                    br.replace_with('\n')
                text = review.text.strip()
                if text:
                    all_review_texts.append(text)
            
            # 穴場度の判定処理
            score, max_score, reasons, is_hidden_gem = self.evaluate_hidden_gem_score(all_review_texts)
            
            return {
                "name": sauna_name,
                "url": url,
                "review_count": len(all_review_texts),
                "score": score,
                "max_score": max_score,
                "is_hidden_gem": is_hidden_gem,
                "reasons": reasons
            }
            
        except Exception as e:
            print(f"サウナ分析エラー: {str(e)}")
            print(traceback.format_exc())
            return {"error": f"サウナの分析中にエラーが発生しました: {str(e)}"}

    def evaluate_hidden_gem_score(self, review_texts: list) -> tuple:
        """レビューテキストから穴場度を判定する"""
        score = 0
        max_score = 5
        reasons = []
        
        # レビューの数をチェック（少ないほど穴場度が高い）
        review_count = len(review_texts)
        if review_count < 10:
            score += 1
            reasons.append(f"レビュー数が少ない（{review_count}件）")
        elif review_count < 20:
            score += 0.5
            reasons.append(f"比較的レビュー数が少ない（{review_count}件）")
        else:
            reasons.append(f"レビュー数が多い（{review_count}件）")
            
        # キーワードの出現頻度をチェック
        keyword_matches = {}
        for keyword in HIDDEN_GEM_KEYWORDS:
            count = 0
            for text in review_texts:
                if keyword in text:
                    count += 1
            if count > 0:
                keyword_percentage = (count / review_count) * 100
                keyword_matches[keyword] = keyword_percentage
        
        # 「穴場」という単語が直接使われている場合、大きくスコアアップ
        if '穴場' in keyword_matches and keyword_matches['穴場'] > 10:
            score += 2
            reasons.append(f"「穴場」という表現が複数のレビューで使用されている ({keyword_matches['穴場']:.1f}%)")
        elif '穴場' in keyword_matches:
            score += 1
            reasons.append(f"「穴場」という表現が使用されている ({keyword_matches['穴場']:.1f}%)")
            
        # その他のキーワードでスコアアップ（最大1.5点）
        keyword_score = 0
        for keyword, percentage in keyword_matches.items():
            if keyword != '穴場' and percentage > 5:
                if keyword_score < 1.5:
                    keyword_score += 0.5
                reasons.append(f"「{keyword}」に関する言及がある ({percentage:.1f}%)")
                
        score += keyword_score
        
        # 混雑していないことを示すキーワードの出現をチェック
        crowd_keywords = ['空いている', '空いてる', '空き', '並ばず', '待たず', 'すいてる', 'すいている']
        crowd_score = 0
        
        for keyword in crowd_keywords:
            for text in review_texts:
                if keyword in text:
                    if crowd_score < 0.5:  # 最大0.5点
                        crowd_score += 0.25
                    if not any(keyword in reason for reason in reasons):
                        reasons.append(f"混雑していないという言及がある")
                    break
                    
        score += crowd_score
        
        # スコア上限を設定
        score = min(score, max_score)
        
        # 穴場かどうかの判定（スコア3.5以上で穴場と判定）
        is_hidden_gem = score >= 3.5
        
        # スコアが低い場合の理由を追加
        if score < 3.5:
            if not reasons or all("数が多い" in reason for reason in reasons):
                reasons.append("穴場を示す特徴が見つかりませんでした")
                
        return score, max_score, reasons, is_hidden_gem
        
    async def scrape_sauna_reviews(self, base_url="https://sauna-ikitai.com/search/saunas?prefecture%5B%5D=13", start_page=1, end_page=3):
        """指定したページ範囲のサウナ施設のレビューをスクレイピングする"""
        results = []
        total_reviews = 0
        
        try:
            if VERBOSE_LOGGING:
                print(f"スクレイピング開始: {base_url} (ページ {start_page}～{end_page})")
            
            for page in range(start_page, end_page + 1):
                # ページURLを構築
                page_url = f"{base_url}&page={page}" if page > 1 else base_url
                
                if VERBOSE_LOGGING:
                    print(f"ページ {page} をスクレイピング中... URL: {page_url}")
                
                # 非同期HTTPクライアントでHTMLを取得
                async with aiohttp.ClientSession() as session:
                    async with session.get(page_url, headers=self.headers) as response:
                        if response.status != 200:
                            print(f"エラー: ページ {page} の取得に失敗。ステータスコード: {response.status}")
                            continue
                            
                        html = await response.text()
                        
                # HTMLをBeautifulSoupで解析
                soup = BeautifulSoup(html, 'html.parser')
                
                # サウナ施設のカードを抽出
                review_cards = soup.select('.p-post-list__item')
                
                if not review_cards:
                    print(f"ページ {page}: レビューカードが見つかりませんでした")
                    continue
                
                if VERBOSE_LOGGING:
                    print(f"ページ {page}: {len(review_cards)} 件のレビューカードを検出")
                
                # 各レビューカードの情報を抽出
                for card in review_cards:
                    try:
                        # サウナ名を取得
                        sauna_elem = card.select_one('.p-post-list__sauna-name')
                        if not sauna_elem:
                            continue
                            
                        sauna_name = sauna_elem.get_text(strip=True)
                        
                        # サウナURLを取得
                        sauna_url_elem = card.select_one('.p-post-list__sauna-name a')
                        sauna_url = ""
                        if sauna_url_elem:
                            sauna_url = sauna_url_elem.get('href', '')
                            
                        # レビューテキストを取得
                        review_elem = card.select_one('.p-post-list__text')
                        if not review_elem:
                            continue
                            
                        review_text = review_elem.get_text(strip=True)
                        
                        # 一意のレビューIDを生成
                        review_id = str(uuid.uuid4())
                        
                        # 隠れた名店関連のキーワードを含むか確認
                        has_hidden_gem_keyword = any(keyword in review_text for keyword in self.hidden_gem_keywords)
                        
                        # レビュー情報を結果リストに追加
                        results.append({
                            'review_id': review_id,
                            'sauna_name': sauna_name,
                            'sauna_url': sauna_url,
                            'review_text': review_text,
                            'has_hidden_gem_keyword': has_hidden_gem_keyword
                        })
                        
                        total_reviews += 1
                        
                    except Exception as e:
                        if VERBOSE_LOGGING:
                            print(f"レビュー抽出エラー: {str(e)}")
                
                # ページ間の待機時間（サーバー負荷軽減のため）
                if page < end_page:
                    await asyncio.sleep(1)
            
            if VERBOSE_LOGGING:
                print(f"スクレイピング完了: {total_reviews} 件のレビューを抽出")
                
            return results
            
        except Exception as e:
            print(f"スクレイピング処理エラー: {str(e)}")
            return []
    
    async def get_hidden_gem_reviews_test(self, count=5, fallback_to_regular=True):
        """隠れた名店のレビューを取得する（本番用）"""
        # 本番モードでは実際にWebからデータを取得
        print(f"サイトからデータ取得中...")
        
        base_url = "https://sauna-ikitai.com/search/saunas?prefecture%5B%5D=13"  # 東京都のサウナ
        
        try:
            # 最大2ページ分のレビューをスクレイピング
            all_reviews = await self.scrape_sauna_reviews(base_url=base_url, start_page=1, end_page=2)
            
            if not all_reviews:
                print("レビュー取得失敗。テストデータを使用します。")
                return self._get_test_reviews(count)
            
            print(f"{len(all_reviews)}件のレビューを取得しました")
            
            # 隠れた名店のキーワードを含むレビューをフィルタリング
            hidden_gem_reviews = [r for r in all_reviews if r.get('has_hidden_gem_keyword', False)]
            
            if hidden_gem_reviews:
                # キーワードを含むレビューがある場合
                print(f"{len(hidden_gem_reviews)}件の隠れた名店レビューが見つかりました")
                return hidden_gem_reviews[:count]  # 指定数まで返す
            elif fallback_to_regular:
                # キーワードを含むレビューがない場合は通常のレビューを返す
                print("隠れた名店レビューが見つからないため、通常のレビューを返します")
                return all_reviews[:count]  # 通常のレビューを指定数まで返す
            else:
                print("隠れた名店レビューが見つかりませんでした")
                return []
                
        except Exception as e:
            print(f"レビュー取得エラー: {str(e)}")
            print("テストデータを使用します")
            # エラー時はテストデータを返す
            return self._get_test_reviews(count)
    
    def _get_test_reviews(self, count=5):
        """テスト用のレビューデータを生成"""
        reviews = [
            {
                "review_id": "test-1",
                "sauna_name": "サウナ&スパ 北欧",
                "sauna_url": "https://sauna-ikitai.com/saunas/1",
                "review_text": "平日の午前中に行くと空いていて穴場です。水風呂が最高に気持ちいい。",
                "has_hidden_gem_keyword": True
            },
            {
                "review_id": "test-2",
                "sauna_name": "天然温泉 テルマー湯",
                "sauna_url": "https://sauna-ikitai.com/saunas/2",
                "review_text": "隠れた名店という感じではないですが、サウナの温度が高くて汗がよく出ます。",
                "has_hidden_gem_keyword": True
            },
            {
                "review_id": "test-3",
                "sauna_name": "サウナセンター",
                "sauna_url": "https://sauna-ikitai.com/saunas/3",
                "review_text": "こじんまりとした施設ですが、人が少なくてゆっくりできます。穴場スポットです。",
                "has_hidden_gem_keyword": True
            },
            {
                "review_id": "test-4",
                "sauna_name": "ひだまりの湯",
                "sauna_url": "https://sauna-ikitai.com/saunas/4",
                "review_text": "静かな環境で、サウナと水風呂の温度差が絶妙。混雑していないのでのんびりできます。",
                "has_hidden_gem_keyword": True
            },
            {
                "review_id": "test-5",
                "sauna_name": "森のサウナ",
                "sauna_url": "https://sauna-ikitai.com/saunas/5",
                "review_text": "穴場です。自然に囲まれたロケーションで、ととのい椅子から森が見えます。",
                "has_hidden_gem_keyword": True
            },
            {
                "review_id": "test-6",
                "sauna_name": "アーバンスパ",
                "sauna_url": "https://sauna-ikitai.com/saunas/6", 
                "review_text": "都心にある穴場のサウナ。人が少ないので、ゆっくりととのえます。",
                "has_hidden_gem_keyword": True
            },
            {
                "review_id": "test-7",
                "sauna_name": "湯処 和みの里",
                "sauna_url": "https://sauna-ikitai.com/saunas/7",
                "review_text": "穴スポのように落ち着いた雰囲気。地元の人に愛されている感じがいい。",
                "has_hidden_gem_keyword": True
            }
        ]
        # 指定した数だけ返す
        return reviews[:min(count, len(reviews))]

    async def analyze_sauna_url(self, url):
        """サウナイキタイのURLからサウナの隠れた名店スコアを分析する"""
        print(f"分析開始: {url}")
        
        try:
            # URLからサウナ施設の情報を取得
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status != 200:
                        return {
                            "success": False,
                            "message": f"エラー: ステータスコード {response.status}"
                        }
                        
                    html = await response.text()
                    
            # HTMLを解析
            soup = BeautifulSoup(html, 'html.parser')
            
            # サウナ施設名を取得
            sauna_name_elem = soup.select_one('h1.p-saunaDetail__title')
            if not sauna_name_elem:
                return {
                    "success": False,
                    "message": "施設名が見つかりませんでした"
                }
                
            sauna_name = sauna_name_elem.get_text(strip=True)
            
            # レビューを取得
            reviews = []
            review_cards = soup.select('.p-saunaDetail__reviewContent')
            
            for card in review_cards[:10]:  # 最大10件のレビューを取得
                review_text_elem = card.select_one('.p-saunaDetail__reviewText')
                if review_text_elem:
                    review_text = review_text_elem.get_text(strip=True)
                    reviews.append(review_text)
            
            # 隠れた名店スコアを算出
            hidden_gem_score = 0
            keyword_matches = []
            
            for review in reviews:
                for keyword in self.hidden_gem_keywords:
                    if keyword in review:
                        hidden_gem_score += 1
                        keyword_matches.append(keyword)
            
            # 平均スコアを計算（レビューあたりの隠れた名店キーワード出現率）
            if reviews:
                avg_score = hidden_gem_score / len(reviews)
            else:
                avg_score = 0
            
            # レビュー数に基づいてスコアを調整（レビュー数が多いほど信頼性が高い）
            if reviews:
                adjusted_score = avg_score * min(1, len(reviews) / 5)
            else:
                adjusted_score = 0
            
            # 100点満点に換算（50%をベースラインとする）
            final_score = min(100, int(adjusted_score * 200))
            
            # 結果を返す
            result = {
                "success": True,
                "sauna_name": sauna_name,
                "review_count": len(reviews),
                "hidden_gem_keywords": list(set(keyword_matches)),
                "hidden_gem_score": final_score,
                "message": f"{sauna_name}の隠れた名店スコアは{final_score}点です",
                "is_hidden_gem": final_score >= 50
            }
            
            print(f"分析完了: {sauna_name} (スコア: {final_score})")
            return result
            
        except Exception as e:
            print(f"分析エラー: {str(e)}")
            return {
                "success": False,
                "message": f"分析中にエラーが発生しました: {str(e)}"
            } 