from bs4 import BeautifulSoup
import re
from pathlib import Path
from app.config import TEST_HTML_PATHS, HIDDEN_GEM_KEYWORDS
from app.models.database import save_review
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

    async def analyze_specific_sauna(self, file_path: str) -> dict:
        """特定のサウナの穴場評価を行う（ローカルファイル用 - 機能1）"""
        try:
            all_review_texts = []
            
            # HTMLファイルを読み込む
            with open(file_path, "r", encoding="utf-8") as f:
                html = f.read()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # レビューテキストを取得
            reviews = soup.select('div.p-postCard_body p.p-postCard_text')
            print(f"レビュー要素を検索: {len(reviews)}件見つかりました")
            
            for review in reviews:
                # 改行を適切に処理
                for br in review.find_all('br'):
                    br.replace_with('\n')
                text = review.text.strip()
                if text:
                    all_review_texts.append(text)
                    print(f"レビュー取得: {text[:100]}...")
            
            print(f"取得した総レビュー数: {len(all_review_texts)}")
            
            # キーワード分析
            keyword_counts = {}
            total_score = 0
            found_keywords = []
            
            for review_text in all_review_texts:
                for keyword, weight in HIDDEN_GEM_KEYWORDS.items():
                    count = len(re.findall(keyword, review_text))
                    if count > 0:
                        if keyword not in keyword_counts:
                            keyword_counts[keyword] = 0
                            found_keywords.append(keyword)
                        keyword_counts[keyword] += count
                        total_score += count * weight
            
            normalized_score = total_score / len(all_review_texts) if all_review_texts else 0
            is_hidden_gem = normalized_score >= 0.5
            
            # 5点満点のスコアに変換
            five_point_score = round(normalized_score * 5, 1)
            
            reasons = []
            if found_keywords:
                reasons.append(f"レビューで「{'」「'.join(found_keywords)}」などの穴場キーワードが見つかりました")
                for keyword, count in keyword_counts.items():
                    reasons.append(f"「{keyword}」が{count}回言及されています")
            else:
                reasons.append("穴場を示すキーワードは見つかりませんでした")
            
            return {
                "is_hidden_gem": is_hidden_gem,
                "score": five_point_score,
                "max_score": 5.0,
                "reasons": reasons,
                "review_count": len(all_review_texts)
            }
                    
        except Exception as e:
            print(f"サウナ分析中にエラーが発生: {str(e)}")
            return {"error": f"エラーが発生しました: {str(e)}"}

    async def analyze_sauna(self, url: str) -> dict:
        """URLからサウナ施設の穴場評価を行う（機能1）"""
        try:
            print(f"サウナURL分析開始: {url}")
            all_review_texts = []
            sauna_name = "不明なサウナ"
            
            # 3ページ分のURLを生成（投稿が複数ページある場合）
            urls = [
                url,  # page1
                f"{url}?page=2",  # page2
                f"{url}?page=3"   # page3
            ]
            
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # まず1ページ目を取得して施設名を抽出
                async with session.get(urls[0]) as response:
                    if response.status != 200:
                        print(f"ページ取得エラー: {response.status} - {urls[0]}")
                        return {"error": f"ページ取得エラー: {response.status}"}
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # サウナ施設名を取得
                    name_elem = soup.select_one('h1.p-saunaDetailHeader_heading')
                    if name_elem:
                        sauna_name = name_elem.text.strip()
                        print(f"サウナ施設名: {sauna_name}")
            
                # 3ページ分のレビューを取得
                for page_url in urls:
                    print(f"ページ分析中: {page_url}")
                    try:
                        async with session.get(page_url) as response:
                            if response.status != 200:
                                print(f"ページ取得エラー: {response.status} - {page_url}")
                                continue
                            
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # レビューテキストを取得
                            reviews = soup.select('p.p-postCard_text')
                            print(f"{page_url}: {len(reviews)}件のレビューを発見")
                            
                            for review in reviews:
                                for br in review.find_all('br'):
                                    br.replace_with('\n')
                                text = review.text.strip()
                                if text:
                                    all_review_texts.append(text)
                                    print(f"レビュー取得: {text[:100]}...")
                        
                        await asyncio.sleep(1)  # 各ページ取得後に1秒待機
                    except Exception as e:
                        print(f"ページ処理中にエラー: {str(e)} - {page_url}")
                        continue
            
            print(f"取得した総レビュー数: {len(all_review_texts)}")
            
            # キーワード分析
            keyword_counts = {}
            total_score = 0
            found_keywords = []
            
            for review_text in all_review_texts:
                for keyword, weight in HIDDEN_GEM_KEYWORDS.items():
                    count = len(re.findall(keyword, review_text))
                    if count > 0:
                        if keyword not in keyword_counts:
                            keyword_counts[keyword] = 0
                            found_keywords.append(keyword)
                        keyword_counts[keyword] += count
                        total_score += count * weight
            
            normalized_score = total_score / len(all_review_texts) if all_review_texts else 0
            is_hidden_gem = normalized_score >= 0.5
            
            # 5点満点のスコアに変換
            five_point_score = round(normalized_score * 5, 1)
            
            reasons = []
            if found_keywords:
                reasons.append(f"レビューで「{'」「'.join(found_keywords)}」などの穴場キーワードが見つかりました")
                for keyword, count in keyword_counts.items():
                    reasons.append(f"「{keyword}」が{count}回言及されています")
            else:
                reasons.append("穴場を示すキーワードは見つかりませんでした")
            
            return {
                "name": sauna_name,
                "is_hidden_gem": is_hidden_gem,
                "score": five_point_score,
                "max_score": 5.0,
                "reasons": reasons,
                "review_count": len(all_review_texts)
            }
                
        except Exception as e:
            print(f"サウナ分析中にエラーが発生: {str(e)}")
            print(f"エラーの詳細:\n{traceback.format_exc()}")
            return {"error": f"エラーが発生しました: {str(e)}"}

    async def get_hidden_gem_reviews_test(self):
        """レビューから穴場サウナを見つける（機能2）"""
        try:
            hidden_gem_reviews = []
            
            # テスト用HTMLファイルを読み込む
            for test_file in TEST_HTML_PATHS:
                test_path = Path(test_file)
                print(f"処理対象ファイル: {test_path}")
                print(f"ファイルの存在確認: {test_path.exists()}")
                
                if test_path.exists():
                    print(f"テストファイル {test_path} を読み込みます")
                    
                    # HTMLファイルを読み込む
                    with open(test_path, "r", encoding="utf-8") as f:
                        html = f.read()
                        print(f"HTMLファイルの長さ: {len(html)} 文字")
                    
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # レビューの取得（投稿カードを取得）
                    review_elements = soup.select('div.p-postCard')
                    print(f"レビュー要素数: {len(review_elements)}")
                    
                    for i, review in enumerate(review_elements):
                        try:
                            print(f"\nレビュー {i+1} の処理開始")
                            # サウナ施設情報の取得（リンクを探す）
                            facility_link = review.select_one('strong.p-postCard_facility a')
                            
                            if facility_link:
                                sauna_name = facility_link.text.strip()
                                sauna_url = facility_link.get('href', '')
                                print(f"サウナ施設名: {sauna_name}")
                                
                                if not sauna_url.startswith('http'):
                                    sauna_url = f"{self.base_url}{sauna_url}"
                                
                                # レビューテキストの取得
                                review_text_elem = review.select_one('p.p-postCard_text')
                                if review_text_elem:
                                    # 改行を適切に処理
                                    review_text = ''
                                    for element in review_text_elem.contents:
                                        if isinstance(element, str):
                                            review_text += element.strip()
                                        elif element.name == 'br':
                                            review_text += '\n'
                                    
                                    review_text = review_text.strip()
                                    print(f"レビューテキスト（先頭100文字）: {review_text[:100]}")
                                    
                                    # キーワードチェック - 大文字小文字を区別しない
                                    found_keywords = []
                                    for keyword in HIDDEN_GEM_KEYWORDS.keys():
                                        if keyword in review_text:
                                            found_keywords.append(keyword)
                                            print(f"キーワード「{keyword}」を発見")
                                    
                                    # キーワードが見つからない場合でもレビューを返す（デバッグ用）
                                    if True or len(found_keywords) > 0:
                                        print(f"レビューを追加: {sauna_name}")
                                        # ユニークなレビューIDを生成
                                        review_id = f"{sauna_url.split('/')[-1]}_{len(hidden_gem_reviews)}"
                                        
                                        # データベースに保存 - エラーが発生してもレビューは返す
                                        try:
                                            await save_review(review_id, sauna_name, review_text)
                                        except Exception as e:
                                            print(f"レビュー保存中にエラー: {str(e)}")
                                        
                                        hidden_gem_reviews.append({
                                            "name": sauna_name,
                                            "url": sauna_url,
                                            "review": review_text,
                                            "keywords": found_keywords
                                        })
                                else:
                                    print("レビューテキストが見つかりません")
                            else:
                                print("サウナ施設リンクが見つかりません")
                        except Exception as e:
                            print(f"個別レビューの処理中にエラー: {str(e)}")
                            print(traceback.format_exc())
                            continue
                else:
                    print(f"テストファイル {test_path} が見つかりません")
            
            print(f"合計 {len(hidden_gem_reviews)} 件のレビューを取得しました")
            return hidden_gem_reviews
        except Exception as e:
            print(f"テスト実行中にエラーが発生: {e}")
            print(f"エラーの詳細:\n{traceback.format_exc()}")
            return []

    async def get_hidden_gem_reviews(self, base_url=None, max_pages=3, start_page=1, end_page=None):
        """実サイトからのレビュー取得（本番用）
        
        Args:
            base_url: スクレイピング対象のベースURL（デフォルト: 東京都の穴場サウナ）
            max_pages: 最大取得ページ数（デフォルト: 3）
            start_page: 開始ページ番号（デフォルト: 1）
            end_page: 終了ページ番号（デフォルト: start_page + max_pages - 1）
        """
        if not base_url:
            base_url = "https://sauna-ikitai.com/posts?prefecture%5B%5D=tokyo&keyword=%E7%A9%B4%E5%A0%B4"
        
        # 終了ページが指定されていない場合は、開始ページ + max_pages - 1 を使用
        if end_page is None:
            end_page = start_page + max_pages - 1
        
        results = []
        total_reviews = 0
        
        try:
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
                                
                                # データベースに保存
                                await save_review(review_id, sauna_name, review_text)
                                total_reviews += 1
                                
                                # 結果リストに追加
                                results.append({
                                    "id": review_id,
                                    "name": sauna_name,
                                    "url": sauna_url,
                                    "review": review_text,
                                    "keywords": [kw for kw in HIDDEN_GEM_KEYWORDS.keys() if kw in review_text]
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