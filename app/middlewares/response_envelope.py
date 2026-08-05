import json
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    """
    Middleware tự động bọc mọi JSON Response của /api/v1 thành dạng Envelope chuẩn:
    {
      "status_code": 200,
      "success": true,
      "message": "Thao tác thành công.",
      "data": ...
    }
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        
        # Bỏ qua các đường dẫn không phải API v1 hoặc các đường dẫn xuất file nhị phân
        if not path.startswith("/api/v1") or "/export/" in path:
            return await call_next(request)

        response = await call_next(request)

        # Chỉ áp dụng cho các response có Content-Type là application/json và HTTP Status 2xx
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Đọc body của response
        body_bytes = b""
        async for chunk in response.body_iterator:
            body_bytes += chunk

        try:
            body_json = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            # Nếu không parse được JSON, trả về nguyên bản
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        # Nếu response đã là envelope (có đủ status_code, success, data) thì giữ nguyên
        if isinstance(body_json, dict) and "status_code" in body_json and "success" in body_json and "data" in body_json:
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        # Xây dựng message phù hợp
        msg = "Thao tác thành công."
        if isinstance(body_json, dict) and "message" in body_json and isinstance(body_json["message"], str):
            msg = body_json.pop("message")

        # Bọc dữ liệu thành envelope chuẩn
        envelope = {
            "status_code": response.status_code,
            "success": True,
            "message": msg,
            "data": body_json
        }

        new_content = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        headers = dict(response.headers)
        headers["content-length"] = str(len(new_content))

        return Response(
            content=new_content,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json"
        )


async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Xử lý các ngoại lệ HTTPException theo chuẩn Envelope.
    """
    detail_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status_code": exc.status_code,
            "success": False,
            "message": detail_msg,
            "data": None
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Xử lý lỗi validation dữ liệu đầu vào (422) theo chuẩn Envelope.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "success": False,
            "message": "Dữ liệu yêu cầu không hợp lệ.",
            "data": exc.errors()
        }
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """
    Xử lý các lỗi ngoại lệ chưa được bắt (500 Internal Server Error) theo chuẩn Envelope.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "success": False,
            "message": f"Đã xảy ra lỗi hệ thống: {str(exc)}",
            "data": None
        }
    )
