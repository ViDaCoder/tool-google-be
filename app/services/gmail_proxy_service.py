from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.models.gmail import GmailAccount
from app.models.proxy import Proxy
from app.models.gmail_proxy import GmailProxy

async def get_or_assign_proxy_for_gmail(db: AsyncSession, gmail_id: int) -> Proxy | None:
    """
    Đảm bảo 1 Gmail chỉ hoạt động trên 1 Proxy cố định (lưu vào bảng gmail_proxies).
    Và 1 Proxy chỉ được gắn cho tối đa 3 Gmails.
    Nếu không có Proxy nào thỏa mãn (hoặc tất cả đều đã đủ 3 Gmails), trả về None (để trống).
    KHÔNG BAO GIỜ làm xáo trộn các phân bổ đã có của Gmail khác.
    """
    # 1. Kiểm tra xem Gmail này đã được gán Proxy cố định trong DB chưa
    stmt = select(GmailProxy).where(GmailProxy.gmail_id == gmail_id)
    res = await db.execute(stmt)
    existing_binding = res.scalars().first()

    if existing_binding:
        # Nếu đã có binding, lấy đúng Proxy cố định đó
        proxy_res = await db.execute(select(Proxy).where(Proxy.id == existing_binding.proxy_id))
        proxy = proxy_res.scalars().first()
        if proxy and proxy.status == "Hoạt động":
            return proxy
        
        # Nếu Proxy bị "Hết hạn", "Không hoạt động" hoặc đã bị xóa -> Xóa liên kết cũ để tái phân bổ cho Gmail này
        await db.delete(existing_binding)
        await db.commit()

    # 2. Nếu chưa có Binding (hoặc vừa xóa binding cũ do hết hạn), tìm Proxy đang HOẠT ĐỘNG có dưới 3 Gmails
    active_proxies_res = await db.execute(select(Proxy).where(Proxy.status == "Hoạt động").order_by(Proxy.id.asc()))
    active_proxies = active_proxies_res.scalars().all()

    for p in active_proxies:
        # Đếm số lượng Gmails hiện tại đang sử dụng Proxy này
        count_stmt = select(func.count(GmailProxy.id)).where(GmailProxy.proxy_id == p.id)
        count_res = await db.execute(count_stmt)
        current_count = count_res.scalar() or 0

        if current_count < 3:
            # Proxy này thỏa điều kiện (dưới 3 Gmails), tạo liên kết cố định mới
            new_binding = GmailProxy(gmail_id=gmail_id, proxy_id=p.id)
            db.add(new_binding)
            await db.commit()
            return p

    # 3. Nếu không có Proxy hoạt động nào thỏa mãn (tất cả đều đã đầy 3/3 hoặc không có proxy), trả về None
    return None

async def ensure_all_gmails_assigned(db: AsyncSession):
    """
    Duyệt qua tất cả Gmails trong CSDL, nếu Gmail nào chưa được phân bổ Proxy thì tự động gán Proxy thỏa mãn.
    """
    stmt = select(GmailAccount).order_by(GmailAccount.id.asc())
    res = await db.execute(stmt)
    gmails = res.scalars().all()
    for g in gmails:
        await get_or_assign_proxy_for_gmail(db, g.id)

async def get_gmail_proxy_map(db: AsyncSession) -> dict[str, str]:
    """
    Trả về Dict ánh xạ Email -> Proxy String ("IP:PORT") hoặc rỗng "" cho tất cả các Gmails.
    """
    await ensure_all_gmails_assigned(db)
    stmt = select(GmailAccount)
    res = await db.execute(stmt)
    gmails = res.scalars().all()

    mapping = {}
    for g in gmails:
        p = await get_or_assign_proxy_for_gmail(db, g.id)
        if p:
            if p.username and p.password:
                mapping[g.email.lower()] = f"{p.ip}:{p.port}:{p.username}:{p.password}"
            else:
                mapping[g.email.lower()] = f"{p.ip}:{p.port}"
        else:
            mapping[g.email.lower()] = ""

    return mapping
