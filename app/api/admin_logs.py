from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, delete

from app.database import get_db
from app.models.log import SystemLog
from app.services.auth import get_current_user

router = APIRouter(prefix="/admin/logs", tags=["Admin Logs"])

@router.get("")
async def get_system_logs(
    limit: int = 100,
    offset: int = 0,
    log_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Lấy danh sách nhật ký hệ thống (Chỉ dành riêng cho tài khoản Admin).
    Tự động dọn dẹp các nhật ký quá 3 ngày. Hỗ trợ phân trang và lọc theo log_type.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập chức năng này. Chỉ tài khoản quản trị mới có thể theo dõi logs."
        )
        
    # 1. Tự động xóa các bản ghi nhật ký quá 3 ngày (created_at < NOW() - 3 days)
    try:
        three_days_ago = datetime.now() - timedelta(days=3)
        await db.execute(delete(SystemLog).where(SystemLog.created_at < three_days_ago))
        await db.commit()
    except Exception as cleanup_err:
        print(f"[Warning] Failed to cleanup logs older than 3 days: {cleanup_err}")
        await db.rollback()

    # 2. Truy vấn danh sách nhật ký
    query = select(SystemLog)
    if log_type:
        query = query.where(SystemLog.log_type == log_type)
        
    # Lấy tổng số dòng để phân trang ở Client
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0
    
    # Lấy danh sách kết quả theo limit/offset
    query = query.order_by(SystemLog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id": log.id,
                "title": log.title,
                "meta": log.meta,
                "logType": log.log_type,
                "createdAt": log.created_at
            } for log in logs
        ]
    }


@router.delete("", status_code=status.HTTP_200_OK)
async def clear_system_logs(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Xóa toàn bộ nhật ký hệ thống trong Database (Chỉ dành riêng cho Admin).
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xóa nhật ký hệ thống."
        )

    try:
        await db.execute(delete(SystemLog))
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xóa toàn bộ nhật ký hệ thống: {str(e)}"
        )

    return {"message": "Đã xóa toàn bộ nhật ký hệ thống thành công."}
