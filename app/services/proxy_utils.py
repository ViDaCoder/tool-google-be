import re
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

def parse_proxy_config(proxy_input: str | dict | None) -> dict | None:
    """
    Chuẩn hóa bất kỳ định dạng Proxy nào thành dict chuẩn cho Playwright:
    - IP:PORT (vd: 222.254.101.54:42220) -> {"server": "http://222.254.101.54:42220"}
    - IP:PORT:USER:PASS (vd: 222.254.101.54:42220:MELCQP:KsEZzd) -> {"server": "http://222.254.101.54:42220", "username": "MELCQP", "password": "KsEZzd"}
    - http://user:pass@ip:port
    - http://ip:port
    - socks5://...
    """
    if not proxy_input:
        return None

    if isinstance(proxy_input, dict):
        if "server" in proxy_input:
            return proxy_input
        return None

    if not isinstance(proxy_input, str):
        return None

    proxy_str = proxy_input.strip()
    if not proxy_str or proxy_str.lower() in ("direct", "ip máy chủ (direct)", "none", "null", ""):
        return None

    # Trường hợp IP:PORT:USER:PASS (vd: 222.254.101.54:42220:MELCQP:KsEZzd)
    clean_str = re.sub(r'^(http|https|socks4|socks5)://', '', proxy_str, flags=re.IGNORECASE)
    parts = clean_str.split(":")

    if len(parts) == 4:
        ip, port, user, password = parts
        return {
            "server": f"http://{ip.strip()}:{port.strip()}",
            "username": user.strip(),
            "password": password.strip()
        }

    if len(parts) == 2 and parts[0].replace(".", "").isdigit():
        ip, port = parts
        return {
            "server": f"http://{ip.strip()}:{port.strip()}"
        }

    # Nếu có tiền tố URL chuẩn hoặc user:pass@ip:port
    full_url = proxy_str
    if not re.match(r'^(http|https|socks4|socks5)://', proxy_str, re.IGNORECASE):
        full_url = f"http://{proxy_str}"

    try:
        parsed = urlparse(full_url)
        if parsed.hostname and parsed.port:
            scheme = parsed.scheme if parsed.scheme else "http"
            server = f"{scheme}://{parsed.hostname}:{parsed.port}"
            proxy_dict = {"server": server}
            if parsed.username:
                proxy_dict["username"] = parsed.username
            if parsed.password:
                proxy_dict["password"] = parsed.password
            return proxy_dict
    except Exception as e:
        print(f"[Proxy Parser Warning] urlparse error: {e}")

    return {"server": full_url}


async def get_proxy_config_for_gmail(db: AsyncSession, gmail_email: str) -> dict | None:
    """
    Tra cứu đối tượng Proxy trong CSDL gán cho tài khoản Gmail này.
    Trả về dict chuẩn Playwright.
    """
    if not db or not gmail_email:
        return None

    from app.models.gmail import GmailAccount
    from app.models.gmail_proxy import GmailProxy
    from app.models.proxy import Proxy

    try:
        res_g = await db.execute(select(GmailAccount).where(GmailAccount.email == gmail_email.strip().lower()))
        gmail_acc = res_g.scalars().first()
        if not gmail_acc:
            return None

        res_gp = await db.execute(select(GmailProxy).where(GmailProxy.gmail_id == gmail_acc.id))
        binding = res_gp.scalars().first()
        if not binding:
            return None

        res_p = await db.execute(select(Proxy).where(Proxy.id == binding.proxy_id))
        proxy_obj = res_p.scalars().first()
        if not proxy_obj:
            return None

        server = f"http://{proxy_obj.ip}:{proxy_obj.port}"
        p_dict = {"server": server}
        if proxy_obj.username and proxy_obj.password:
            p_dict["username"] = proxy_obj.username
            p_dict["password"] = proxy_obj.password

        return p_dict
    except Exception as e:
        print(f"[Proxy Utils DB Error] {e}")
        return None
