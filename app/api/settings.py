import os
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
    Lấy cấu hình hiện tại trong cơ sở dữ liệu (AI Engines & Thư mục ảnh).
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
        review_system_prompt=settings_dict.get("review_system_prompt", ""),
        image_folder_path=settings_dict.get("image_folder_path", r"C:\hinh_google")
    )

@router.put("", response_model=SystemSettingsResponse)
async def update_settings(
    request_data: SystemSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Cập nhật cấu hình mới cho hệ thống và tự động tạo thư mục ảnh trên đĩa nếu chưa tồn tại.
    """
    updates = {
        "analytics_api_key": request_data.analytics_api_key,
        "analytics_model_id": request_data.analytics_model_id,
        "analytics_system_prompt": request_data.analytics_system_prompt,
        "review_api_key": request_data.review_api_key,
        "review_model_id": request_data.review_model_id,
        "review_system_prompt": request_data.review_system_prompt,
        "image_folder_path": request_data.image_folder_path
    }
    
    for key, value in updates.items():
        if value is not None:
            clean_val = value.strip() if isinstance(value, str) else value

            # Nếu là đường dẫn thư mục ảnh -> Kiểm tra và tự động khởi tạo thư mục trên ổ đĩa nếu chưa tồn tại
            if key == "image_folder_path" and clean_val:
                try:
                    if not os.path.exists(clean_val):
                        os.makedirs(clean_val, exist_ok=True)
                        print(f"[Settings API] Successfully created image directory: {clean_val}")

                    # Tự động tạo thư mục con cho tất cả doanh nghiệp trong CSDL
                    from app.models.business import Business
                    from app.services.poster import to_unsigned_snake_case
                    biz_res = await db.execute(select(Business))
                    all_bizs = biz_res.scalars().all()
                    for biz in all_bizs:
                        folder_name = to_unsigned_snake_case(biz.name)
                        if folder_name:
                            b_dir = os.path.join(clean_val, folder_name)
                            os.makedirs(b_dir, exist_ok=True)
                            print(f"[Settings API] Auto-created business subfolder: {b_dir}")
                except Exception as mkdir_err:
                    print(f"[Settings API Error] Could not create directory {clean_val}: {mkdir_err}")

            # Tìm hoặc tạo mới bản ghi trong CSDL
            result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
            record = result.scalars().first()
            if record:
                record.value = clean_val
            else:
                record = SystemSetting(key=key, value=clean_val)
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
