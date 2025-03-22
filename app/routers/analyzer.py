from fastapi import APIRouter, Form
from app.services.scraper import SaunaScraper

router = APIRouter()
scraper = SaunaScraper()

@router.post("/analyze")
async def analyze(url: str = Form(...)):
    """既存のサウナの穴場評価APIエンドポイント"""
    result = await scraper.analyze_sauna(url)
    return result 