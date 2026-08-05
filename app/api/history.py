import csv
import io
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.history import ReviewHistory
from app.schemas.review import ReviewHistoryResponse, ReviewHistoryCreate
from app.services.auth import get_current_user

router = APIRouter(prefix="/history", tags=["Review History"])

@router.get("", response_model=list[ReviewHistoryResponse])
async def get_history(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Lấy toàn bộ danh sách lịch sử các bài review ĐÃ ĐĂNG THÀNH CÔNG, sắp xếp theo thời gian mới nhất.
    """
    result = await db.execute(select(ReviewHistory).order_by(ReviewHistory.created_at.desc()))
    history_records = result.scalars().all()
    return history_records

@router.post("", response_model=ReviewHistoryResponse, status_code=status.HTTP_201_CREATED)
async def record_posted_history(
    history_data: ReviewHistoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Ghi nhận bài review ĐÃ ĐĂNG THÀNH CÔNG vào bảng Lịch sử bài viết review.
    """
    import uuid
    from app.services.logs import log_system_activity
    
    history_id = f"hist_{uuid.uuid4().hex[:16]}"
    
    new_history = ReviewHistory(
        id=history_id,
        business_id=history_data.business_id,
        business_name=history_data.business_name,
        category=history_data.category,
        url=history_data.url,
        tone=history_data.tone,
        language=history_data.language,
        length=history_data.length,
        custom_keywords=history_data.custom_keywords,
        reviews=[r.model_dump() for r in history_data.reviews]
    )
    
    db.add(new_history)
    
    try:
        await db.commit()
        await db.refresh(new_history)
        
        await log_system_activity(
            db,
            "Lưu lịch sử đăng bài",
            f"Người dùng {current_user.email} đã hoàn tất đăng review thành công cho '{history_data.business_name}'.",
            "success"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lưu lịch sử đăng bài vào cơ sở dữ liệu: {str(e)}"
        )
        
    return new_history

@router.delete("/{history_id}", status_code=status.HTTP_200_OK)
async def delete_history_item(
    history_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Xóa một bản ghi lịch sử sinh review theo ID.
    """
    result = await db.execute(select(ReviewHistory).where(ReviewHistory.id == history_id))
    history_item = result.scalars().first()
    
    if not history_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bản ghi lịch sử yêu cầu."
        )
        
    try:
        await db.delete(history_item)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xóa lịch sử: {str(e)}"
        )
        
    return {"message": "Xóa bản ghi lịch sử sinh review thành công."}

@router.get("/{history_id}/export/csv")
async def export_history_csv(
    history_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Xuất danh sách reviews đã sinh ra thành tệp tin định dạng CSV để tải về.
    """
    result = await db.execute(select(ReviewHistory).where(ReviewHistory.id == history_id))
    history_item = result.scalars().first()
    
    if not history_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lịch sử để xuất dữ liệu."
        )
        
    output = io.StringIO()
    # Ghi UTF-8 BOM để Excel hiển thị đúng font Tiếng Việt
    output.write('\ufeff')
    writer = csv.writer(output)
    
    # Tiêu đề cột
    writer.writerow(["ID Review", "Số sao (Rating)", "Nội dung đánh giá (Content)"])
    
    # Ghi dữ liệu
    for r in history_item.reviews:
        writer.writerow([r.get("id"), r.get("rating"), r.get("content")])
        
    csv_data = output.getvalue()
    output.close()
    
    return StreamingResponse(
        iter([csv_data.encode("utf-8")]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=export_{history_id}.csv",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@router.get("/{history_id}/export/txt")
async def export_history_txt(
    history_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Xuất danh sách reviews đã sinh ra thành tệp tin định dạng văn bản thuần túy (TXT) để tải về.
    """
    result = await db.execute(select(ReviewHistory).where(ReviewHistory.id == history_id))
    history_item = result.scalars().first()
    
    if not history_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lịch sử để xuất dữ liệu."
        )
        
    text_lines = []
    text_lines.append(f"DOANH NGHIỆP: {history_item.business_name}")
    text_lines.append(f"LĨNH VỰC: {history_item.category or 'Không có'}")
    text_lines.append(f"TONE: {history_item.tone} | NGÔN NGỮ: {history_item.language} | ĐỘ DÀI: {history_item.length}")
    text_lines.append(f"THỜI GIAN SINH: {history_item.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    text_lines.append("="*60)
    text_lines.append("\n")
    
    for r in history_item.reviews:
        text_lines.append(f"ĐÁNH GIÁ #{r.get('id')} ({r.get('rating')} sao):")
        text_lines.append(r.get("content", "").strip())
        text_lines.append("-"*40)
        text_lines.append("\n")
        
    txt_data = "\n".join(text_lines)
    
    return StreamingResponse(
        iter([txt_data.encode("utf-8")]),
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename=export_{history_id}.txt",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )
