import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.models.gmail import GmailAccount
from app.schemas.gmail import GmailCreate, GmailUpdate, GmailResponse, GmailBulkCreateRequest
from app.interface.crypto_service import ICryptoService
from app.services.auth import admin_required, get_current_user, get_crypto_service

router = APIRouter(prefix="/admin/gmails", tags=["Admin Gmail Management"])

@router.get("/proxy-map", status_code=status.HTTP_200_OK)
async def get_gmail_proxy_mappings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lấy bảng ánh xạ 1 Gmail -> 1 Proxy cố định từ bảng gmail_proxies."""
    from app.services.gmail_proxy_service import get_gmail_proxy_map
    mapping = await get_gmail_proxy_map(db)
    return mapping

@router.post("/open-login", status_code=status.HTTP_200_OK)
async def open_gmail_interactive_login(
    db: AsyncSession = Depends(get_db),
    crypto_service: ICryptoService = Depends(get_crypto_service),
    current_user: User = Depends(admin_required)
):
    """
    Mở trình duyệt Chrome hiển thị cho người dùng tự do đăng nhập Gmail mới & OTP.
    Backend tự động bóc tách email, lưu Profile Session và tự tạo bản ghi CSDL.
    """
    from app.services.gmail_auth import open_interactive_login_service

    auth_res = await open_interactive_login_service(db)

    if not auth_res.get("success") or not auth_res.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=auth_res.get("message", "Chưa hoàn tất đăng nhập trên trình duyệt Chrome.")
        )

    email_clean = auth_res["email"]

    # Kiểm tra xem tài khoản đã tồn tại trong DB chưa
    result = await db.execute(select(GmailAccount).where(GmailAccount.email == email_clean))
    existing = result.scalars().first()

    if existing:
        existing.status = "Hoạt động"
        await db.commit()
        await db.refresh(existing)
        return {
            "success": True,
            "message": f"Đã nạp thành công phiên Gmail: {email_clean}",
            "gmail": existing
        }

    # Nếu chưa có, tạo bản ghi mới trong CSDL
    new_gmail = GmailAccount(
        email=email_clean,
        password=crypto_service.encrypt("SessionSaved"),
        status="Hoạt động"
    )
    db.add(new_gmail)
    await db.commit()
    await db.refresh(new_gmail)

    return {
        "success": True,
        "message": f"Đã thêm thành công tài khoản Gmail: {email_clean}",
        "gmail": new_gmail
    }

@router.get("", response_model=list[GmailResponse])
async def list_gmails(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lấy danh sách tất cả tài khoản Gmail kèm theo Proxy được phân bổ cố định."""
    from app.services.gmail_proxy_service import get_or_assign_proxy_for_gmail
    result = await db.execute(select(GmailAccount).order_by(GmailAccount.id.asc()))
    gmails = result.scalars().all()
    
    response_list = []
    for g in gmails:
        p = await get_or_assign_proxy_for_gmail(db, g.id)
        proxy_str = f"{p.ip}:{p.port}:{p.username}:{p.password}" if (p and p.username and p.password) else (f"{p.ip}:{p.port}" if p else None)
        response_list.append(
            GmailResponse(
                id=g.id,
                email=g.email,
                status=g.status,
                proxy=proxy_str,
                created_at=g.created_at,
                updated_at=g.updated_at
            )
        )
    return response_list

@router.post("", response_model=GmailResponse, status_code=status.HTTP_201_CREATED)
async def create_gmail(
    gmail_data: GmailCreate,
    db: AsyncSession = Depends(get_db),
    crypto_service: ICryptoService = Depends(get_crypto_service),
    current_user: User = Depends(admin_required)
):
    """
    Thêm tài khoản Gmail mới (Chỉ dành cho Admin).
    Mật khẩu sẽ được mã hóa đối xứng trước khi lưu vào cơ sở dữ liệu.
    Tự động gán Proxy cố định thỏa mãn (dưới 3 Gmails), để trống nếu không có Proxy thỏa mãn.
    """
    email_clean = gmail_data.email.strip().lower()
    
    # Kiểm tra email trùng lặp
    result = await db.execute(select(GmailAccount).where(GmailAccount.email == email_clean))
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài khoản Gmail này đã được lưu trên hệ thống."
        )

    # Mã hóa mật khẩu
    encrypted_password = crypto_service.encrypt(gmail_data.password)

    new_gmail = GmailAccount(
        email=email_clean,
        password=encrypted_password,
        status=gmail_data.status
    )

    db.add(new_gmail)
    await db.commit()
    await db.refresh(new_gmail)

    # Thử tự động phân bổ Proxy cho Gmail mới (Tối đa 3 Gmails/Proxy, không xáo trộn Gmail khác)
    from app.services.gmail_proxy_service import get_or_assign_proxy_for_gmail
    p = await get_or_assign_proxy_for_gmail(db, new_gmail.id)
    proxy_str = f"{p.ip}:{p.port}" if p else None

    # Tự động nạp phiên đăng nhập Google cho tài khoản Gmail vừa thêm
    from app.services.gmail_auth import init_gmail_session
    asyncio.create_task(init_gmail_session(db, email_clean, gmail_data.password))

    return GmailResponse(
        id=new_gmail.id,
        email=new_gmail.email,
        status=new_gmail.status,
        proxy=proxy_str,
        created_at=new_gmail.created_at,
        updated_at=new_gmail.updated_at
    )

@router.post("/bulk-create", status_code=status.HTTP_201_CREATED)
async def bulk_create_gmails(
    payload: GmailBulkCreateRequest,
    db: AsyncSession = Depends(get_db),
    crypto_service: ICryptoService = Depends(get_crypto_service),
    current_user: User = Depends(admin_required)
):
    """
    Thêm tài khoản Gmail hàng loạt (Mỗi tài khoản 1 dòng).
    Tự động lọc trùng, mã hóa mật khẩu, lưu status='Cần xác minh'
    và phân bổ Proxy tự động (tối đa 3 Gmails/Proxy, để trống nếu không có Proxy).
    """
    raw_lines = payload.raw_text.strip().splitlines()
    if not raw_lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nội dung danh sách Gmail dán vào đang trống."
        )

    added_count = 0
    skipped_count = 0

    for line in raw_lines:
        clean_line = line.strip()
        if not clean_line:
            continue

        if "|" in clean_line:
            parts = [p.strip() for p in clean_line.split("|")]
        elif "\t" in clean_line:
            parts = [p.strip() for p in clean_line.split("\t")]
        elif "," in clean_line:
            parts = [p.strip() for p in clean_line.split(",")]
        else:
            parts = [p.strip() for p in clean_line.split(":")]

        if not parts or not parts[0]:
            continue

        email = parts[0].strip().lower()
        if "@" not in email:
            email = f"{email}@gmail.com"

        if not email.endswith("@gmail.com"):
            continue

        # Không cần mật khẩu khi thêm hàng loạt (đặt mặc định "SessionSaved")
        password = "SessionSaved"

        # Kiểm tra trùng lặp Email
        existing_res = await db.execute(select(GmailAccount).where(GmailAccount.email == email))
        if existing_res.scalars().first():
            skipped_count += 1
            continue

        encrypted_pass = crypto_service.encrypt(password)
        new_gmail = GmailAccount(
            email=email,
            password=encrypted_pass,
            status="Cần xác minh"
        )
        db.add(new_gmail)
        await db.commit()
        await db.refresh(new_gmail)

        added_count += 1

    # Phân bổ Proxy tự động cho các Gmail vừa thêm (Tối đa 3 Gmails/Proxy)
    from app.services.gmail_proxy_service import ensure_all_gmails_assigned
    await ensure_all_gmails_assigned(db)

    return {
        "success": True,
        "added": added_count,
        "skipped": skipped_count,
        "message": f"Đã thêm thành công {added_count} tài khoản Gmail (Bỏ qua {skipped_count} tài khoản trùng lặp). Đã tự động phân bổ Proxy."
    }

@router.post("/{gmail_id}/init-session", status_code=status.HTTP_200_OK)
async def trigger_init_gmail_session(
    gmail_id: int,
    db: AsyncSession = Depends(get_db),
    crypto_service: ICryptoService = Depends(get_crypto_service),
    current_user: User = Depends(admin_required)
):
    """Kích hoạt tự động nạp phiên đăng nhập Google cho tài khoản Gmail (Chỉ dành cho Admin)."""
    result = await db.execute(select(GmailAccount).where(GmailAccount.id == gmail_id))
    gmail = result.scalars().first()

    if not gmail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tài khoản Gmail."
        )

    raw_password = crypto_service.decrypt(gmail.password)
    from app.services.gmail_auth import init_gmail_session
    auth_res = await init_gmail_session(db, gmail.email, raw_password)

    if auth_res.get("status"):
        gmail.status = auth_res["status"]
        await db.commit()

    return {
        "success": auth_res.get("success", False),
        "message": auth_res.get("message", "Đã khởi chạy quy trình nạp phiên Gmail.")
    }

@router.put("/{gmail_id}", response_model=GmailResponse)
async def update_gmail(
    gmail_id: int,
    gmail_data: GmailUpdate,
    db: AsyncSession = Depends(get_db),
    crypto_service: ICryptoService = Depends(get_crypto_service),
    current_user: User = Depends(admin_required)
):
    """Cập nhật tài khoản Gmail (Chỉ dành cho Admin)."""
    result = await db.execute(select(GmailAccount).where(GmailAccount.id == gmail_id))
    gmail = result.scalars().first()

    if not gmail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tài khoản Gmail."
        )

    # Cập nhật thông tin
    gmail.status = gmail_data.status
    if gmail_data.password is not None:
        gmail.password = crypto_service.encrypt(gmail_data.password)

    await db.commit()
    await db.refresh(gmail)

    # Nếu cập nhật mật khẩu mới, tự động nạp lại phiên Google
    if gmail_data.password is not None:
        from app.services.gmail_auth import init_gmail_session
        asyncio.create_task(init_gmail_session(db, gmail.email, gmail_data.password))

    return gmail

@router.delete("/{gmail_id}", status_code=status.HTTP_200_OK)
async def delete_gmail(
    gmail_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Xóa tài khoản Gmail khỏi hệ thống (Chỉ dành cho Admin)."""
    result = await db.execute(select(GmailAccount).where(GmailAccount.id == gmail_id))
    gmail = result.scalars().first()

    if not gmail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tài khoản Gmail."
        )

    email_clean = gmail.email.strip().lower().replace("@", "_")
    await db.delete(gmail)
    await db.commit()

    # Dọn dẹp toàn bộ thư mục Profile lưu trữ của Gmail đó trên ổ cứng
    try:
        import os, shutil
        user_data_dir = os.path.join(os.getcwd(), ".browser_profiles", email_clean)
        if os.path.exists(user_data_dir):
            shutil.rmtree(user_data_dir, ignore_errors=True)
    except Exception as e:
        print(f"[Delete Gmail] Clean profile dir error: {e}")

    return {
        "success": True,
        "message": "Đã xóa tài khoản Gmail khỏi hệ thống thành công."
    }
