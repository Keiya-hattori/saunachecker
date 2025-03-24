from bs4 import BeautifulSoup
import re
from pathlib import Path
from app.config import TEST_HTML_PATHS, HIDDEN_GEM_KEYWORDS
import aiohttp
import asyncio
import traceback
import time

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
        
    async def scrape_sauna_reviews(self, base_url=None, start_page=1, end_page=3):
        """指定されたページ範囲のサウナレビューをスクレイピングする
        
        Args:
            base_url: スクレイピング対象のベースURL（デフォルト: 東京都の穴場サウナ）
            start_page: 開始ページ番号（デフォルト: 1）
            end_page: 終了ページ番号（デフォルト: 3）
            
        Returns:
            スクレイピングしたレビューのリスト
        """
        if not base_url:
            base_url = "https://sauna-ikitai.com/posts?prefecture%5B%5D=tokyo&keyword=%E7%A9%B4%E5%A0%B4"
        
        results = []
        total_reviews = 0
        
        try:
            print(f"スクレイピングを開始します: {base_url} ページ {start_page} から {end_page} まで")
            
            for page in range(start_page, end_page + 1):
                page_url = f"{base_url}&page={page}" if page > 1 else base_url
                print(f"ページ {page} をスクレイピング中: {page_url}")
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(page_url, headers=self.headers) as response:
                        if response.status != 200:
                            print(f"ページの取得に失敗: {page_url}, ステータス: {response.status}")
                            continue
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # レビューカードを取得
                        review_cards = soup.select('div.p-postCard')
                        if not review_cards:
                            print(f"レビューが見つかりませんでした: {page_url}")
                            break
                        
                        print(f"ページ {page} で {len(review_cards)} 件のレビューカードを発見")
                        
                        for card in review_cards:
                            try:
                                # サウナ施設名を取得
                                sauna_link = card.select_one('a[href*="/saunas/"]')
                                if not sauna_link:
                                    continue
                                    
                                sauna_name = sauna_link.get_text(strip=True)
                                sauna_url = "https://sauna-ikitai.com" + sauna_link['href']
                                
                                # レビューテキストを取得
                                review_text_elem = card.select_one('p.p-postCard_text')
                                if not review_text_elem:
                                    continue
                                    
                                # 改行を処理
                                for br in review_text_elem.find_all('br'):
                                    br.replace_with('\n')
                                
                                review_text = review_text_elem.get_text(strip=True)
                                if not review_text:
                                    continue
                                
                                # レビューIDを生成（URL+タイムスタンプなど一意になるもの）
                                review_id = f"{sauna_url.split('/')[-1]}_{int(time.time())}_{total_reviews}"
                                
                                total_reviews += 1
                                
                                # キーワードチェック
                                keywords = [kw for kw in HIDDEN_GEM_KEYWORDS.keys() if kw in review_text]
                                
                                # 結果リストに追加
                                results.append({
                                    "id": review_id,
                                    "name": sauna_name,
                                    "url": sauna_url,
                                    "review": review_text,
                                    "keywords": keywords
                                })
                                
                            except Exception as e:
                                print(f"レビュー処理中にエラー: {str(e)}")
                                continue
                
                # 連続アクセスを避けるため待機
                await asyncio.sleep(2)
            
            print(f"合計 {total_reviews} 件のレビューを取得しました")
            return results
        
        except Exception as e:
            print(f"スクレイピング中にエラーが発生: {str(e)}")
            print(traceback.format_exc())
            return [] 