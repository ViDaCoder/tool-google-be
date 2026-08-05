from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.models.proxy import Proxy
from app.schemas.proxy import ProxyCreate, ProxyUpdate, ProxyResponse
from app.services.auth import admin_required, get_current_user

router = APIRouter(prefix="/admin/proxies", tags=["Admin Proxy Management"])

import ipaddress
import re

def is_valid_ip_or_domain(ip_str: str) -> bool:
    ip_clean = ip_str.strip()
    try:
        ipaddress.ip_address(ip_clean)
        return True
    except ValueError:
        pass
    if re.match(r'^([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$', ip_clean):
        return True
    return False

@router.get("", response_model=list[ProxyResponse])
async def list_proxies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lấy danh sách tất cả Proxies kèm theo danh sách Gmails đang gắn với từng Proxy."""
    from app.models.gmail import GmailAccount
    from app.models.gmail_proxy import GmailProxy
    from app.services.gmail_proxy_service import ensure_all_gmails_assigned

    # Đảm bảo tất cả các Gmails hiện có đều đã được gán Proxy trong gmail_proxies
    await ensure_all_gmails_assigned(db)

    result = await db.execute(select(Proxy).order_by(Proxy.id.desc()))
    proxies = result.scalars().all()
    
    response_list = []
    for p in proxies:
        # Lấy danh sách Gmail đang liên kết với Proxy này trong bảng gmail_proxies
        gmail_stmt = (
            select(GmailAccount.email)
            .join(GmailProxy, GmailProxy.gmail_id == GmailAccount.id)
            .where(GmailProxy.proxy_id == p.id)
        )
        gmail_res = await db.execute(gmail_stmt)
        assigned_emails = list(gmail_res.scalars().all())

        response_list.append(
            ProxyResponse(
                id=p.id,
                ip=p.ip,
                port=p.port,
                username=p.username,
                password=p.password,
                status=p.status,
                assigned_gmails=assigned_emails,
                created_at=p.created_at,
                updated_at=p.updated_at
            )
        )
    return response_list

@router.post("", response_model=ProxyResponse, status_code=status.HTTP_201_CREATED)
async def create_proxy(
    proxy_data: ProxyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Thêm Proxy mới (Chỉ dành cho Admin).
    Kiểm tra trùng lặp cặp IP và Port trên hệ thống.
    """
    ip_clean = proxy_data.ip.strip()

    # Bổ sung tính năng thông minh: Nếu người dùng dán nguyên chuỗi IP:PORT:USER:PASS hoặc IP:PORT vào ô IP
    parts = ip_clean.split(":")
    if len(parts) == 4:
        ip_clean = parts[0].strip()
        try:
            proxy_data.port = int(parts[1].strip())
        except ValueError:
            pass
        if not proxy_data.username:
            proxy_data.username = parts[2].strip()
        if not proxy_data.password:
            proxy_data.password = parts[3].strip()
    elif len(parts) == 2 and parts[1].isdigit():
        ip_clean = parts[0].strip()
        proxy_data.port = int(parts[1].strip())
    
    if not is_valid_ip_or_domain(ip_clean):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Địa chỉ IP không hợp lệ. Mỗi phần số của địa chỉ IPv4 phải từ 0 đến 255 (ví dụ: 123.45.67.89)."
        )

    # Kiểm tra trùng lặp IP:Port
    result = await db.execute(
        select(Proxy).where(Proxy.ip == ip_clean, Proxy.port == proxy_data.port)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Địa chỉ Proxy IP:Port này đã tồn tại trên hệ thống."
        )

    new_proxy = Proxy(
        ip=ip_clean,
        port=proxy_data.port,
        username=proxy_data.username.strip() if proxy_data.username else None,
        password=proxy_data.password.strip() if proxy_data.password else None,
        status=proxy_data.status
    )

    db.add(new_proxy)
    await db.commit()
    await db.refresh(new_proxy)
    return new_proxy

@router.put("/{proxy_id}", response_model=ProxyResponse)
async def update_proxy(
    proxy_id: int,
    proxy_data: ProxyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Cập nhật thông tin Proxy (Chỉ dành cho Admin)."""
    result = await db.execute(select(Proxy).where(Proxy.id == proxy_id))
    proxy = result.scalars().first()

    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin Proxy."
        )

    ip_clean = proxy_data.ip.strip()

    # Kiểm tra trùng lặp với Proxy khác nếu IP hoặc Port thay đổi
    if proxy.ip != ip_clean or proxy.port != proxy_data.port:
        dup_result = await db.execute(
            select(Proxy).where(Proxy.ip == ip_clean, Proxy.port == proxy_data.port, Proxy.id != proxy_id)
        )
        if dup_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Địa chỉ Proxy IP:Port này đã tồn tại trên hệ thống."
            )

    # Cập nhật thông tin
    proxy.ip = ip_clean
    proxy.port = proxy_data.port
    proxy.username = proxy_data.username.strip() if proxy_data.username else None
    proxy.password = proxy_data.password.strip() if proxy_data.password else None
    proxy.status = proxy_data.status

    await db.commit()
    await db.refresh(proxy)
    return proxy

@router.delete("/{proxy_id}", status_code=status.HTTP_200_OK)
async def delete_proxy(
    proxy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Xóa Proxy khỏi hệ thống (Chỉ dành cho Admin)."""
    result = await db.execute(select(Proxy).where(Proxy.id == proxy_id))
    proxy = result.scalars().first()

    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin Proxy."
        )

    await db.delete(proxy)
    await db.commit()

    return {
        "success": True,
        "message": "Đã xóa Proxy khỏi hệ thống thành công."
    }

@router.post("/check-all", status_code=status.HTTP_200_OK)
async def trigger_check_all_proxies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Kích hoạt kiểm tra kết nối (ping test) cho toàn bộ Proxy trong hệ thống."""
    from app.services.proxy_checker import check_all_proxies_health
    res = await check_all_proxies_health(db)
    return {
        "success": True,
        "message": f"Đã kiểm tra xong {res['total']} Proxy: {res['active']} Hoạt động, {res['expired']} Hết hạn.",
        "result": res
    }

@router.post("/{proxy_id}/check", status_code=status.HTTP_200_OK)
async def trigger_check_single_proxy(
    proxy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Kích hoạt kiểm tra kết nối cho 1 Proxy cụ thể."""
    result = await db.execute(select(Proxy).where(Proxy.id == proxy_id))
    proxy = result.scalars().first()

    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin Proxy."
        )

    from app.services.proxy_checker import check_single_proxy_health
    res = await check_single_proxy_health(proxy)

    new_status = "Hoạt động" if res["online"] else "Hết hạn"
    proxy.status = new_status
    await db.commit()
    await db.refresh(proxy)

    # Tự động tái phân bổ Proxy mới cho các Gmail có Proxy vừa bị Hết hạn
    from app.services.gmail_proxy_service import ensure_all_gmails_assigned
    await ensure_all_gmails_assigned(db)

    msg = f"Proxy {proxy.ip}:{proxy.port} hoạt động tốt ({res['latency_ms']}ms)" if res['online'] else f"Proxy {proxy.ip}:{proxy.port} không phản hồi (Hết hạn)"

    return {
        "success": res["online"],
        "status": new_status,
        "latency_ms": res["latency_ms"],
        "error": res["error"],
        "message": msg
    }
