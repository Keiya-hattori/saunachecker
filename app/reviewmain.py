from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
from pathlib import Path
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
from datetime import datetime
import json
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
import traceback

app = FastAPI(title="サウナ穴場チェッカー")

# テンプレートとスタティックファイルの設定
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ルートディレクトリの作成
Path("templates").mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)

# テストファイルのディレクトリ設定
test_dir = Path("test_files")
test_dir.mkdir(exist_ok=True)

# 実際のHTMLファイルをtest_filesディレクトリにコピー
test_html_path = test_dir / "real_sauna.html"
if not test_html_path.exists():
    with open("詳細ページ.html", "r", encoding="utf-8") as src:  # ここを修正
        with open(test_html_path, "w", encoding="utf-8") as dst:
            dst.write(src.read())

# 静的ファイルとしてマウント
app.mount("/test_files", StaticFiles(directory="test_files"), name="test_files")

# 穴場キーワードとその重み付け
HIDDEN_GEM_KEYWORDS = {
    '穴場': 2,
    '隠れ家': 2,
    '静か': 1,
    '混んでいない': 1,
    '並ばない': 1,
    'ゆったり': 1,
    '落ち着く': 1,
    '知る人ぞ知る': 2,
    '教えたくない': 2,
    '空いている': 1,
    'のんびり': 1,
    '穴場スポット': 2,
}

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
        self.delay = 2.0

    async def get_sauna_list(self) -> List[str]:
        """サウナ一覧ページからURLを取得"""
        try:
            urls = []
            for page in range(1, 2):  # テスト用に1ページのみ
                await asyncio.sleep(self.delay)
                search_url = f"{self.base_url}/search?ordering=post_counts_desc&page={page}&prefecture%5B0%5D=tokyo"
                print(f"ページ {page} からサウナ一覧を取得中: {search_url}")
                
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    async with session.get(search_url) as response:
                        if response.status != 200:
                            print(f"エラー: ページ {page} でステータスコード {response.status}")
                            continue
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # 正しいセレクタを使用
                        sauna_items = soup.select('div.p-saunaItem > a')
                        print(f"ページ {page} で {len(sauna_items)} 件のサウナリンクを発見")
                        
                        for link in sauna_items:
                            if 'href' in link.attrs:
                                full_url = link['href']
                                urls.append(full_url)
                                print(f"サウナURL追加: {full_url}")
            
            print(f"合計: {len(urls)} 件のサウナURLを取得")
            return urls[:10]  # 最初の10件のみ返す
        except Exception as e:
            print(f"get_sauna_list でエラーが発生: {e}")
            traceback.print_exc()
            return []

    async def get_sauna_info(self, url: str) -> Optional[Dict[str, Any]]:
        """個別のサウナ情報を取得"""
        try:
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    async with session.get(url) as response:
                        if response.status == 202:
                            print(f"ステータス202を受信。{retry_delay}秒後にリトライ: {url}")
                            await asyncio.sleep(retry_delay)
                            continue
                        elif response.status != 200:
                            print(f"エラー: ステータスコード {response.status} for URL {url}")
                            return None
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # サウナ情報の抽出処理
                        name = soup.select_one('h1.p-saunaDetailHeader_heading')
                        name = name.text.strip() if name else "不明"
                        
                        return {
                            "name": name,
                            "url": url,
                            # 他の情報も必要に応じて追加
                        }
            
            print(f"最大リトライ回数を超過: {url}")
            return None
        except Exception as e:
            print(f"get_sauna_info でエラー: {e} - URL: {url}")
            return None

    def _get_empty_sauna_info(self, url: str) -> Dict:
        """エラー時のデフォルト情報を返す"""
        return {
            "name": "データ取得エラー",
            "address": "情報なし",
            "price": "情報なし",
            "url": url,
            "facilities": {},
            "is_hidden_gem": False,
            "review_count": 0
        }

    def _extract_price(self, soup: BeautifulSoup) -> str:
        try:
            price_section = soup.find('th', text=re.compile(r'料金'))
            if price_section:
                price_elem = price_section.find_next('td')
                if price_elem:
                    return price_elem.text.strip()
            return "料金情報なし"
        except Exception as e:
            print(f"Error extracting price: {e}")
            return "料金情報なし"

    def _extract_facilities(self, soup: BeautifulSoup) -> Dict:
        try:
            facilities = {}
            
            # サウナ室情報
            sauna_section = soup.find('div', class_='p-saunaSpecItem--sauna')
            if sauna_section:
                facilities['sauna'] = {
                    'temperature': self._extract_temperature(sauna_section),
                    'capacity': self._extract_capacity(sauna_section),
                    'features': self._extract_features(sauna_section)
                }
                
            # 水風呂情報
            mizuburo_section = soup.find('div', class_='p-saunaSpecItem--mizuburo')
            if mizuburo_section:
                facilities['mizuburo'] = {
                    'temperature': self._extract_temperature(mizuburo_section),
                    'capacity': self._extract_capacity(mizuburo_section),
                    'features': self._extract_features(mizuburo_section)
                }
                
            return facilities
        except Exception as e:
            print(f"Error extracting facilities: {e}")
            return {}

    def _extract_temperature(self, section: BeautifulSoup) -> str:
        try:
            temp_elem = section.find('strong')
            if temp_elem:
                return f"{temp_elem.text}度"
            return "温度情報なし"
        except Exception as e:
            print(f"Error extracting temperature: {e}")
            return "温度情報なし"

    def _extract_capacity(self, section: BeautifulSoup) -> str:
        try:
            capacity_elem = section.find(text=re.compile(r'収容人数'))
            if capacity_elem:
                return capacity_elem.find_next().text.strip()
            return "収容人数情報なし"
        except Exception as e:
            print(f"Error extracting capacity: {e}")
            return "収容人数情報なし"

    def _extract_features(self, section: BeautifulSoup) -> List[str]:
        try:
            features = []
            tags = section.find_all('li', class_='p-tags_tag')
            for tag in tags:
                features.append(tag.text.strip())
            return features
        except Exception as e:
            print(f"Error extracting features: {e}")
            return []

    async def _extract_reviews(self, sauna_id: str) -> List[str]:
        """サ活（レビュー）から穴場情報を抽出"""
        try:
            await asyncio.sleep(self.delay)
            reviews_url = f"{self.base_url}/saunas/{sauna_id}/posts"
            print(f"Fetching reviews from: {reviews_url}")
            
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(reviews_url) as response:
                    if response.status != 200:
                        print(f"Error: Status code {response.status}")
                        return []
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    reviews = []
                    review_elements = soup.find_all('p', class_='p-postCard_text')
                    for review in review_elements:
                        review_text = review.text.strip()
                        if re.search(r'穴場|隠れ家|静か|混んでいない|並ばない|ゆったり|落ち着く|知る人ぞ知る|教えたくない', review_text):
                            reviews.append(review_text)
                    return reviews
        except Exception as e:
            print(f"Error fetching reviews: {e}")
            return []

    def _extract_review_count(self, soup: BeautifulSoup) -> int:
        try:
            # p-localNav_countクラスを持つspan要素を探す
            count_elem = soup.find('span', class_='p-localNav_count')
            if count_elem:
                return int(count_elem.text)
            print("Review count element not found")  # デバッグ用
            return 0
        except Exception as e:
            print(f"Error extracting review count: {e}")
            return 0

    def _check_hidden_gem(self, reviews: List[str]) -> bool:
        return len(reviews) > 0

    async def get_saunas(self) -> List[Dict[str, Any]]:
        """サウナ情報を取得"""
        try:
            urls = await self.get_sauna_list()
            print(f"取得したサウナURL数: {len(urls)}")
            
            # 最初の10件のURLのみを使用
            urls = urls[:10]
            print(f"処理対象のサウナ数: {len(urls)}")
            
            tasks = []
            for url in urls:
                task = asyncio.create_task(self.get_sauna_info(url))
                tasks.append(task)
                await asyncio.sleep(self.delay)  # リクエスト間隔を制御
            
            saunas = await asyncio.gather(*tasks)
            return [sauna for sauna in saunas if sauna is not None]
        except Exception as e:
            print(f"get_saunas でエラーが発生: {e}")
            return []

scraper = SaunaScraper()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/saunas")
async def get_saunas():
    # サウナ情報の取得
    saunas = await scraper.get_saunas()
    print("取得したサウナ数:", len(saunas))  # デバッグ用
    return {"saunas": saunas}

async def analyze_sauna(url: str) -> dict:
    try:
        all_review_texts = []
        
        # 3ページ分のURLを生成
        urls = [
            url,  # page1
            f"{url}?page=2",  # page2
            f"{url}?page=3"   # page3
        ]
        
        for page_url in urls:
            print(f"ページ分析中: {page_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(page_url) as response:
                    if response.status != 200:
                        print(f"ページ取得エラー: {response.status} - {page_url}")
                        continue
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # レビューテキストを取得
                    reviews = soup.select('p.p-postCard_text')
                    for review in reviews:
                        for br in review.find_all('br'):
                            br.replace_with('\n')
                        text = review.text.strip()
                        if text:
                            all_review_texts.append(text)
                            print(f"レビュー取得: {text[:100]}...")
                    
                    await asyncio.sleep(1)  # 各ページ取得後に1秒待機
        
        print(f"取得した総レビュー数: {len(all_review_texts)}")
        
        # キーワード分析（既存のコード）
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
            "name": "テスト用サウナ",
            "is_hidden_gem": is_hidden_gem,
            "score": five_point_score,
            "max_score": 5.0,
            "reasons": reasons,
            "review_count": len(all_review_texts)
        }
                
    except Exception as e:
        print(f"エラーの詳細: {str(e)}")
        print(f"エラーの発生箇所:\n{traceback.format_exc()}")
        return {"error": f"エラーが発生しました: {str(e)}"}

@app.post("/analyze")
async def analyze(url: str = Form(...)):
    result = await analyze_sauna(url)
    return result

# テスト用エンドポイントを追加
@app.get("/test")
async def test_analyze(request: Request):
    """テスト用ページ"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "test_url": "/test_files/real_sauna.html"
        }
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
