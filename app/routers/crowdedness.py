from fastapi import APIRouter, Query
from app.services.crowdedness import CrowdednessService
from app.models.database import get_sauna_ranking, get_sauna_stats_by_name

router = APIRouter()
crowdedness_service = CrowdednessService()

@router.get("/api/crowdedness")
async def get_crowdedness(sauna_name: str = Query(..., description="混雑情報を取得したいサウナの名前")):
    """サウナの混雑情報を取得"""
    try:
        result = await crowdedness_service.get_crowdedness(sauna_name)
        
        # サウナのcrowdedness_statusを更新
        if result and "status" in result:
            await update_sauna_crowdedness_status(sauna_name, result["status"])
        
        return {
            "status": "success",
            "message": "混雑情報を取得しました",
            "crowdedness": result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"混雑情報の取得中にエラーが発生しました: {str(e)}"
        }

async def update_sauna_crowdedness_status(sauna_name, status):
    """サウナの混雑度ステータスを更新"""
    try:
        sauna = await get_sauna_stats_by_name(sauna_name)
        if sauna:
            sauna.crowdedness_status = status
            sauna.save()
    except Exception as e:
        print(f"混雑度ステータス更新中にエラー: {str(e)}") 