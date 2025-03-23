import aiohttp
import re
import json
import asyncio
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import urllib.parse
import random
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import platform
import sys
import traceback
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# Render上での注意事項:
# 1. ChromeとChromedriverをインストールするためのbuild commandを追加する必要があります
#    例: apt-get update && apt-get install -y chromium-driver chromium
# 2. 環境変数RENDER=Trueを設定してこのスクリプトにRender環境であることを伝える
# 3. Chrome関連のパスを設定する環境変数:
#    CHROMIUM_PATH=/usr/bin/chromium
#    CHROMEDRIVER_PATH=/usr/bin/chromedriver

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class CrowdednessService:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.cache = {}  # サウナ名と混雑情報のキャッシュ
        self.cache_expiry = {}  # キャッシュの有効期限（5分）
        
        # Seleniumの設定
        self.browser = None
        self.setup_selenium()
        
    def setup_selenium(self):
        """Seleniumの設定を行う"""
        try:
            logger.info("Seleniumの設定を開始します")
            
            # Renderの環境変数をチェック
            is_render = os.environ.get('RENDER', 'False') == 'True'
            
            logger.info(f"環境: {'Render' if is_render else 'ローカル'}")
            
            # Render環境では常にブラウザをNoneに設定（モックデータを使用）
            if is_render:
                logger.info("Render環境では現在Chromeが利用できないため、モックデータを使用します")
                self.browser = None
                return
                
            # 以下はローカル環境のみで実行
            # Chromeのオプション設定
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # ヘッドレスモードで実行
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument(f"user-agent={self.headers['User-Agent']}")
            chrome_options.add_argument("--lang=ja")  # 日本語設定
            
            logger.info("Chrome options設定完了")
            
            try:
                # ローカル環境用の設定
                chromedriver_path = self._get_chromedriver_path()
                if not chromedriver_path:
                    # 手動インストールに失敗した場合、webdriver-managerを試す
                    service = Service(ChromeDriverManager().install())
                    logger.info("webdriver-managerを使用してChromeDriverをインストールしました")
                else:
                    service = Service(executable_path=chromedriver_path)
                    logger.info(f"ローカルのChromeDriverを使用: {chromedriver_path}")
                
                # ブラウザインスタンスを作成
                logger.info("webdriver.Chrome初期化開始")
                self.browser = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Seleniumの設定が完了しました。ブラウザインスタンスを作成しました。")
            except Exception as e:
                logger.error(f"ChromeDriverのインストールに失敗しました: {str(e)}")
                logger.error(traceback.format_exc())
                self.browser = None
        except Exception as e:
            logger.error(f"Seleniumの設定中にエラーが発生しました: {str(e)}")
            # スタックトレースも出力
            logger.error(traceback.format_exc())
            # フォールバックとしてブラウザはNoneのままにする
            self.browser = None
    
    def _get_chromedriver_path(self):
        """ChromeDriverのパスを取得する"""
        try:
            logger.info("ChromeDriverのパスを取得します")
            
            # プロジェクトルートディレクトリのパス
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            logger.info(f"プロジェクトルートディレクトリ: {base_dir}")
            
            # OSに応じたChromeDriverのファイル名
            if platform.system() == "Windows":
                chromedriver_name = "chromedriver.exe"
            else:
                chromedriver_name = "chromedriver"
            
            logger.info(f"OS: {platform.system()}, ChromeDriverファイル名: {chromedriver_name}")
            
            # drivers/chromedriverディレクトリを作成
            drivers_dir = os.path.join(base_dir, "drivers", "chromedriver")
            logger.info(f"ドライバーディレクトリ: {drivers_dir}")
            
            try:
                os.makedirs(drivers_dir, exist_ok=True)
                logger.info(f"ディレクトリ作成/確認完了: {drivers_dir}")
            except Exception as e:
                logger.error(f"ディレクトリ作成中にエラー: {str(e)}")
            
            # ChromeDriverのパス
            chromedriver_path = os.path.join(drivers_dir, chromedriver_name)
            logger.info(f"ChromeDriverのパス: {chromedriver_path}")
            
            # ファイルが存在するか確認
            if os.path.exists(chromedriver_path):
                logger.info(f"既存のChromeDriverを使用: {chromedriver_path}")
                return chromedriver_path
            
            logger.warning(f"ChromeDriverが存在しないため、手動でダウンロードする必要があります: {chromedriver_path}")
            logger.warning("以下のサイトからダウンロードできます: https://chromedriver.chromium.org/downloads")
            logger.warning(f"または次のURLから直接ダウンロード: https://storage.googleapis.com/chrome-for-testing-public/134.0.6998.88/win32/chromedriver-win32.zip")
            logger.warning(f"ダウンロードしたファイルを次のパスに配置してください: {chromedriver_path}")
            
            return None
            
        except Exception as e:
            logger.error(f"ChromeDriverパスの取得中にエラー: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def get_crowdedness(self, sauna_name):
        """サウナ名を元にGoogle Mapsで検索し、混雑度情報を取得"""
        try:
            logger.info(f"サウナ名: {sauna_name} の混雑度情報を取得します")
            
            # キャッシュをチェック
            current_time = time.time()
            if sauna_name in self.cache and self.cache_expiry.get(sauna_name, 0) > current_time:
                logger.info(f"キャッシュから混雑情報を取得: {sauna_name}")
                return self.cache[sauna_name]
            
            # Seleniumが設定されていない場合は模擬データを返す
            if self.browser is None:
                logger.warning("Seleniumが設定されていないため、模擬データを返します")
                return await self._generate_mock_data(sauna_name)
            
            # Google Mapsで検索
            encoded_query = urllib.parse.quote(f"{sauna_name}")
            maps_url = f"https://www.google.com/maps/search/{encoded_query}"
            
            logger.info(f"Seleniumを使用して混雑度情報を検索中: {maps_url}")
            
            # 非同期処理をブロッキングコールに変換
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: self._scrape_with_selenium(maps_url, sauna_name))
            
            # 結果にエラーがない場合はキャッシュに保存
            if "error" not in result:
                self.cache[sauna_name] = result
                self.cache_expiry[sauna_name] = current_time + 300  # 5分間
                logger.info(f"混雑情報をキャッシュに保存しました: {sauna_name}")
            
            return result
                    
        except Exception as e:
            logger.error(f"混雑度情報取得中にエラー: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # エラーが発生した場合は模擬データを返す
            return await self._generate_mock_data(sauna_name)
    
    def _scrape_with_selenium(self, url, sauna_name):
        """Seleniumを使用してGoogleマップから混雑度情報をスクレイピング"""
        try:
            logger.info(f"URLを読み込み中: {url}")
            self.browser.get(url)
            
            # ページが読み込まれるまで待機
            logger.info("ページの読み込みを待機中...")
            WebDriverWait(self.browser, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Googleマップが読み込まれるまで少し待機
            logger.info("Google Mapsの読み込みのため5秒待機")
            time.sleep(5)
            
            # 検索結果一覧から最初の施設をクリックして詳細ページに遷移
            try:
                logger.info("検索結果一覧から最初の施設を探しています...")
                # 検索結果のセレクタはGoogleマップの仕様変更で変わることがあるため、複数のセレクタを試す
                selectors = [
                    "div.Nv2PK",                 # 一般的な検索結果アイテム
                    "a[jsaction*='mouseup']",    # クリック可能なリンク要素
                    "div.DxyBCb",                # リスト内の施設アイテム
                    "div[role='article']",       # リスト内の記事アイテム
                    "div.tTVLSc"                 # リスト内のカード型アイテム
                ]
                
                first_result = None
                for selector in selectors:
                    try:
                        logger.info(f"セレクタ「{selector}」で検索結果を探しています...")
                        results = self.browser.find_elements(By.CSS_SELECTOR, selector)
                        if results:
                            first_result = results[0]
                            logger.info(f"セレクタ「{selector}」で検索結果が見つかりました")
                            break
                    except Exception as e:
                        logger.info(f"セレクタ「{selector}」での検索中にエラー: {str(e)}")
                
                if first_result:
                    logger.info("最初の検索結果をクリックします")
                    # JavaScriptを使用してクリック（より確実）
                    self.browser.execute_script("arguments[0].click();", first_result)
                    
                    # 詳細ページの読み込みを待機
                    logger.info("詳細ページの読み込みを待機中...")
                    time.sleep(5)  # 追加の待機時間
                    
                    # 詳細ページに遷移したことを確認するためにURLの変化をチェック
                    new_url = self.browser.current_url
                    logger.info(f"詳細ページURL: {new_url}")
                    
                    # 詳細ページ特有の要素が表示されるまで待機
                    try:
                        WebDriverWait(self.browser, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 
                                                            "div[aria-label*='情報' i], div[aria-label*='混雑' i], div.gm2-body-2"))
                        )
                        logger.info("詳細ページの要素が読み込まれました")
                    except Exception as e:
                        logger.warning(f"詳細ページの要素待機中にエラー: {str(e)}")
                else:
                    logger.warning("検索結果が見つかりませんでした。詳細ページへの遷移をスキップします")
            except Exception as e:
                logger.error(f"詳細ページへの遷移中にエラー: {str(e)}")
                logger.error(traceback.format_exc())
            
            # Googleマップが読み込まれるまでさらに待機
            logger.info("詳細ページの完全な読み込みのためさらに5秒待機")
            time.sleep(5)
            
            # 現在のURLを保存（詳細ページに遷移している場合がある）
            current_url = self.browser.current_url
            logger.info(f"現在のURL: {current_url}")
            
            # デバッグ用にHTMLを保存
            try:
                html_content = self.browser.page_source
                debug_file = 'debug_google_maps_selenium.html'
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logger.info(f"デバッグ用にHTMLを保存しました: {debug_file}")
            except Exception as e:
                logger.error(f"HTMLの保存中にエラー: {str(e)}")
            
            logger.info("Google Mapsページが読み込まれました")
            
            # 混雑度情報を探す
            try:
                logger.info("詳細情報の検索を開始...")
                
                # 詳細ページで混雑度情報を直接探す試み
                try:
                    logger.info("混雑度情報を直接探します...")
                    
                    # 混雑度情報を含む要素を直接探す
                    logger.info("aria-labelに「現在の混雑度」を含む要素を探します")
                    crowd_elements = self.browser.find_elements(By.CSS_SELECTOR, "div[aria-label*='現在の混雑度'], div[role='img'][aria-label*='現在の混雑度']")
                    
                    if crowd_elements:
                        logger.info(f"混雑度の要素が {len(crowd_elements)} 個見つかりました")
                        
                        for element in crowd_elements:
                            try:
                                aria_label = element.get_attribute("aria-label")
                                logger.info(f"混雑度のaria-label: {aria_label}")
                                
                                # パーセンテージとステータスを抽出
                                # 例：「現在の混雑度は 41%、通常は 77% です。」
                                current_match = re.search(r'現在の混雑度は\s*(\d+)%', aria_label)
                                usual_match = re.search(r'通常は\s*(\d+)%', aria_label)
                                
                                if current_match:
                                    current_percentage = int(current_match.group(1))
                                    logger.info(f"現在の混雑度: {current_percentage}%")
                                    
                                    # 通常の混雑度を取得
                                    usual_percentage = int(usual_match.group(1)) if usual_match else max(0, current_percentage - random.randint(5, 15))
                                    logger.info(f"通常の混雑度: {usual_percentage}%")
                                    
                                    # 混雑ステータスを決定
                                    crowd_status = self._get_crowd_status(current_percentage)
                                    
                                    result = {
                                        "current_percentage": current_percentage,
                                        "usual_percentage": usual_percentage,
                                        "maps_url": current_url,
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "status": crowd_status
                                    }
                                    
                                    logger.info(f"混雑度情報を取得しました: 現在 {current_percentage}%, 通常 {usual_percentage}%, ステータス: {crowd_status}")
                                    return result
                            except Exception as e:
                                logger.warning(f"aria-labelの処理中にエラー: {str(e)}")
                    else:
                        logger.info("混雑度情報を含む要素が見つかりませんでした")
                
                except Exception as e:
                    logger.error(f"混雑度情報の直接検索中にエラー: {str(e)}")
                    logger.error(traceback.format_exc())
                
            except Exception as e:
                logger.error(f"詳細情報の検索中にエラー: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 混雑度情報が見つからなかった場合は、NotFoundステータスを返す
            logger.info("混雑度情報が見つからなかったため、情報なしステータスを返します")
            result = {
                "current_percentage": 0,
                "usual_percentage": 0,
                "maps_url": current_url,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "NotFound",
                "message": "こちらのサウナの混雑度はGoogle Mapに表記されていません"
            }
            
            # NotFoundステータスもキャッシュに保存する（無駄な再検索を避けるため）
            current_time = time.time()  # 現在時刻を取得
            self.cache[sauna_name] = result
            self.cache_expiry[sauna_name] = current_time + 86400  # 24時間キャッシュ
            logger.info(f"NotFound情報をキャッシュに保存しました: {sauna_name}")
            
            return result
            
        except Exception as e:
            logger.error(f"Seleniumでのスクレイピング中にエラー: {str(e)}")
            # スタックトレースもログに出力
            import traceback
            logger.error(traceback.format_exc())
            return {"error": f"スクレイピング中にエラーが発生しました: {str(e)}"}
    
    def _generate_mock_data_sync(self, maps_url):
        """模擬データを同期的に生成する（Selenium内で使用）"""
        logger.info("模擬データを生成中...")
        # 現在時刻から混雑度を生成（曜日・時間帯によって変動）
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()  # 0-6 (月-日)
        
        # 時間帯による混雑度の変動（朝・昼・夕方・夜で変化）
        if 6 <= hour < 10:  # 朝
            base_crowd = 30
        elif 10 <= hour < 14:  # 昼
            base_crowd = 60  
        elif 14 <= hour < 17:  # 午後
            base_crowd = 40
        elif 17 <= hour < 21:  # 夕方・夜
            base_crowd = 80
        else:  # 深夜
            base_crowd = 20
        
        # 曜日による変動（平日と週末で変化）
        if weekday >= 5:  # 週末 (5:土, 6:日)
            base_crowd += 20
        
        # ランダム要素を加える（±10%）
        random_factor = random.randint(-10, 10)
        current_percentage = max(0, min(100, base_crowd + random_factor))
        
        # 通常時の混雑度
        usual_percentage = max(0, min(100, base_crowd - 5))
        
        # 結果を整形
        result = {
            "current_percentage": current_percentage,
            "usual_percentage": usual_percentage,
            "maps_url": maps_url,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": self._get_crowd_status(current_percentage),
            "note": "模擬データです"
        }
        
        logger.info(f"生成した模擬混雑度: 現在 {current_percentage}%, 通常 {usual_percentage}%")
        return result
    
    async def _generate_mock_data(self, sauna_name):
        """模擬データを非同期的に生成する（Seleniumが設定されていない場合のフォールバック）"""
        # サウナ名からGoogle Maps URLを生成
        encoded_query = urllib.parse.quote(sauna_name)
        maps_url = f"https://www.google.com/maps/search/{encoded_query}"
        
        # Render環境かチェック
        is_render = os.environ.get('RENDER', 'False') == 'True'
        
        if is_render:
            logger.info(f"Render環境でのモックデータを生成します: {sauna_name}")
            # Render環境ではメッセージを変更
            note = "Render環境では現在混雑度の取得が制限されています。近日中にアップデート予定です。"
        else:
            logger.info(f"サウナ名 {sauna_name} の模擬データを生成します")
            note = "模擬データです"
        
        result = self._generate_mock_data_sync(maps_url)
        result["note"] = note
        return result
    
    def _get_crowd_status(self, percentage):
        """混雑度のパーセンテージからステータスを判定"""
        if percentage == 0:
            return "NotFound"
        elif percentage < 30:
            return "空いています"
        elif percentage < 60:
            return "やや混雑しています"
        elif percentage < 80:
            return "混雑しています"
        else:
            return "非常に混雑しています"

    def __del__(self):
        """デストラクタ - ブラウザを閉じる"""
        if self.browser:
            try:
                logger.info("ブラウザを終了します")
                self.browser.quit()
            except Exception as e:
                logger.error(f"ブラウザの終了中にエラー: {str(e)}")

# クラスの明示的なエクスポートを確認
__all__ = ["CrowdednessService"]