from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.settings import SystemSetting
from app.schemas.settings import SystemSettingsResponse, SystemSettingsUpdate
from app.services.auth import get_current_user

router = APIRouter(prefix="/settings", tags=["System Settings"])

@router.get("", response_model=SystemSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Lấy cấu hình hiện tại của 2 Động cơ AI (Analytics và Review) trong cơ sở dữ liệu.
    """
    result = await db.execute(select(SystemSetting))
    settings_records = result.scalars().all()
    settings_dict = {r.key: r.value for r in settings_records}
    
    return SystemSettingsResponse(
        analytics_api_key=settings_dict.get("analytics_api_key", ""),
        analytics_model_id=settings_dict.get("analytics_model_id", "gemini-2.5-flash"),
        analytics_system_prompt=settings_dict.get("analytics_system_prompt", ""),
        review_api_key=settings_dict.get("review_api_key", ""),
        review_model_id=settings_dict.get("review_model_id", "gemini-1.5-pro"),
        review_system_prompt=settings_dict.get("review_system_prompt", "")
    )

@router.put("", response_model=SystemSettingsResponse)
async def update_settings(
    request_data: SystemSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Cập nhật cấu hình mới cho 2 Động cơ AI.
    """
    updates = {
        "analytics_api_key": request_data.analytics_api_key,
        "analytics_model_id": request_data.analytics_model_id,
        "analytics_system_prompt": request_data.analytics_system_prompt,
        "review_api_key": request_data.review_api_key,
        "review_model_id": request_data.review_model_id,
        "review_system_prompt": request_data.review_system_prompt
    }
    
    for key, value in updates.items():
        if value is not None:
            # Tìm hoặc tạo mới bản ghi
            result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
            record = result.scalars().first()
            if record:
                record.value = value
            else:
                record = SystemSetting(key=key, value=value)
                db.add(record)
                
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lưu cấu hình vào cơ sở dữ liệu: {str(e)}"
        )
        
    # Trả về kết quả mới nhất sau khi cập nhật
    return await get_settings(db, current_user)
