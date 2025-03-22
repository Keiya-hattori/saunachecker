from pathlib import Path

# ディレクトリ設定
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
TEST_FILES_DIR = BASE_DIR / "test_files"

# テスト用のHTMLファイルパス
TEST_HTML_PATHS = [
    TEST_FILES_DIR / "sauna_reviews_page1.html",
    TEST_FILES_DIR / "sauna_reviews_page2.html",
    TEST_FILES_DIR / "sauna_reviews_page3.html"
]

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