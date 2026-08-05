import time
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.proxy import Proxy

TEST_TARGET_URL = "https://www.google.com"

async def check_single_proxy_health(proxy_obj: Proxy) -> dict:
    """
    Kiểm tra kết nối của 1 Proxy tới https://www.google.com (timeout 5s).
    Trả về dict: {"online": bool, "latency_ms": int, "error": str | None}
    """
    if proxy_obj.username and proxy_obj.password:
        proxy_url = f"http://{proxy_obj.username}:{proxy_obj.password}@{proxy_obj.ip}:{proxy_obj.port}"
    else:
        proxy_url = f"http://{proxy_obj.ip}:{proxy_obj.port}"

    start_time = time.time()
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=5.0, verify=False) as client:
            resp = await client.get(TEST_TARGET_URL)
            latency = int((time.time() - start_time) * 1000)
            if resp.status_code < 400 or resp.status_code in (403, 429):
                return {"online": True, "latency_ms": latency, "error": None}
            else:
                return {"online": False, "latency_ms": latency, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"online": False, "latency_ms": latency, "error": str(e)}

async def check_all_proxies_health(db: AsyncSession) -> dict:
    """
    Duyệt qua tất cả Proxies trong CSDL, kiểm tra sức khỏe và cập nhật status:
    'Hoạt động' (nếu sống) hoặc 'Hết hạn' (nếu chết/timeout).
    """
    result = await db.execute(select(Proxy))
    proxies = result.scalars().all()

    active_count = 0
    expired_count = 0
    results_detail = []

    for p in proxies:
        res = await check_single_proxy_health(p)
        new_status = "Hoạt động" if res["online"] else "Hết hạn"
        p.status = new_status
        if res["online"]:
            active_count += 1
        else:
            expired_count += 1

        results_detail.append({
            "id": p.id,
            "ip": p.ip,
            "port": p.port,
            "status": new_status,
            "latency_ms": res["latency_ms"],
            "error": res["error"]
        })

    await db.commit()

    # Tự động tái phân bổ Proxy hoạt động mới cho các Gmail có Proxy vừa bị Hết hạn
    from app.services.gmail_proxy_service import ensure_all_gmails_assigned
    await ensure_all_gmails_assigned(db)

    print(f"[ProxyChecker] Tested {len(proxies)} proxies: {active_count} Hoạt động, {expired_count} Hết hạn.")
    return {
        "total": len(proxies),
        "active": active_count,
        "expired": expired_count,
        "details": results_detail
    }
