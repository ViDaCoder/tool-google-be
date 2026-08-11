import os
import shutil
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.settings import SystemSetting
from app.services.auth import get_current_user

router = APIRouter(prefix="/media", tags=["Media Library Explorer"])

DEFAULT_IMAGE_ROOT = r"C:\hinh_google_new"

@router.get("/files/{file_path:path}")
async def serve_media_file(
    file_path: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Trả về file ảnh thực tế từ ổ đĩa C:\\hinh_google_new
    """
    root_dir = await get_root_image_dir(db)
    safe_rel = os.path.normpath(file_path).lstrip("\\").lstrip("/")
    target_file = os.path.join(root_dir, safe_rel)
    
    if os.path.exists(target_file) and os.path.isfile(target_file):
        return FileResponse(target_file)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File ảnh không tồn tại trên ổ đĩa.")

async def get_root_image_dir(db: AsyncSession) -> str:
    """Lấy đường dẫn thư mục gốc từ DB cấu hình hệ thống, mặc định C:\\hinh_google_new"""
    try:
        res = await db.execute(select(SystemSetting).where(SystemSetting.key == "image_folder_path"))
        setting = res.scalars().first()
        if setting and setting.value and setting.value.strip():
            root_dir = setting.value.strip()
        else:
            root_dir = DEFAULT_IMAGE_ROOT
    except Exception:
        root_dir = DEFAULT_IMAGE_ROOT

    # Tự động tạo thư mục nếu chưa tồn tại
    if not os.path.exists(root_dir):
        try:
            os.makedirs(root_dir, exist_ok=True)
        except Exception as e:
            print(f"[Media Library] Warning creating root dir {root_dir}: {e}")

    return root_dir

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

class DeleteFileRequest(BaseModel):
    rel_path: str

@router.get("/explorer")
async def explore_media_folder(
    subfolder: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Ánh xạ 100% chính xác từ thư mục đĩa thật 'C:\\hinh_google_new' lên giao diện Explorer.
    """
    root_dir = await get_root_image_dir(db)
    
    target_dir = root_dir
    if subfolder:
        # Chống path traversal
        safe_sub = os.path.normpath(subfolder).lstrip("\\").lstrip("/")
        target_dir = os.path.join(root_dir, safe_sub)

    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    folders = []
    files = []

    valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

    try:
        entries = os.scandir(target_dir)
        for entry in entries:
            if entry.is_dir():
                # Đếm số lượng file ảnh bên trong thư mục con
                sub_count = 0
                try:
                    for sub_entry in os.scandir(entry.path):
                        if sub_entry.is_file() and os.path.splitext(sub_entry.name)[1].lower() in valid_extensions:
                            sub_count += 1
                except Exception:
                    pass

                folders.append({
                    "name": entry.name,
                    "rel_path": os.path.relpath(entry.path, root_dir),
                    "full_path": entry.path,
                    "file_count": sub_count
                })
            elif entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in valid_extensions:
                    stat = entry.stat()
                    rel_path = os.path.relpath(entry.path, root_dir).replace("\\", "/")
                    file_url = f"/api/v1/media/files/{rel_path}"
                    
                    import datetime
                    mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M")

                    files.append({
                        "id": rel_path,
                        "filename": entry.name,
                        "rel_path": rel_path,
                        "full_path": entry.path,
                        "url": file_url,
                        "size": format_file_size(stat.st_size),
                        "uploadedAt": mod_time
                    })
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể đọc thư mục trên ổ đĩa: {e}"
        )

    # Sắp xếp danh sách
    folders.sort(key=lambda x: x["name"].lower())
    files.sort(key=lambda x: x["filename"].lower())

    return {
        "root_dir": root_dir,
        "current_subfolder": subfolder or "",
        "folders": folders,
        "files": files
    }

@router.post("/upload")
async def upload_media_file(
    file: UploadFile = File(...),
    subfolder: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Tải file ảnh trực tiếp vào ổ đĩa thật (C:\\hinh_google_new hoặc thư mục con bên trong).
    """
    root_dir = await get_root_image_dir(db)
    
    target_dir = root_dir
    if subfolder:
        safe_sub = os.path.normpath(subfolder).lstrip("\\").lstrip("/")
        target_dir = os.path.join(root_dir, safe_sub)

    os.makedirs(target_dir, exist_ok=True)

    filename = file.filename or f"img_{uuid.uuid4().hex[:8]}.jpg"
    dest_path = os.path.join(target_dir, filename)

    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể lưu file vào đĩa: {e}"
        )

    rel_path = os.path.relpath(dest_path, root_dir).replace("\\", "/")
    file_url = f"/api/v1/media/files/{rel_path}"

    return {
        "filename": filename,
        "full_path": dest_path,
        "rel_path": rel_path,
        "url": file_url
    }

class BatchDeleteRequest(BaseModel):
    rel_paths: list[str]

@router.post("/delete")
async def delete_media_file(
    request_data: DeleteFileRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Xóa file hoặc thư mục trực tiếp trên đĩa thật C:\\hinh_google_new.
    """
    root_dir = await get_root_image_dir(db)
    safe_rel = os.path.normpath(request_data.rel_path).lstrip("\\").lstrip("/")
    target_path = os.path.join(root_dir, safe_rel)

    if os.path.exists(target_path):
        try:
            if os.path.isdir(target_path):
                shutil.rmtree(target_path)
            else:
                os.remove(target_path)
            return {"message": f"Đã xóa thành công: {request_data.rel_path}"}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Không thể xóa mục khỏi đĩa: {e}"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mục không tồn tại trên ổ đĩa."
        )

@router.post("/delete-batch")
async def delete_media_batch(
    request_data: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Xóa hàng loạt file/thư mục trên đĩa thật C:\\hinh_google_new.
    """
    root_dir = await get_root_image_dir(db)
    deleted_count = 0

    for rel_path in request_data.rel_paths:
        safe_rel = os.path.normpath(rel_path).lstrip("\\").lstrip("/")
        target_path = os.path.join(root_dir, safe_rel)
        if os.path.exists(target_path):
            try:
                if os.path.isdir(target_path):
                    shutil.rmtree(target_path)
                else:
                    os.remove(target_path)
                deleted_count += 1
            except Exception as e:
                print(f"[Media Delete Error] Could not delete {target_path}: {e}")

    return {"message": f"Đã xóa {deleted_count} mục khỏi đĩa.", "deleted_count": deleted_count}
