from starlette.responses import JSONResponse


class RequestSizeLimit:
    """Bound input even when Content-Length is omitted or dishonest."""
    def __init__(self, app, max_bytes=11 * 1024 * 1024):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH", "PUT"}:
            return await self.app(scope, receive, send)
        messages, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                response = JSONResponse({"detail": "요청 크기가 제한을 초과했습니다."}, status_code=413)
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break
        position = 0
        async def replay():
            nonlocal position
            if position < len(messages):
                message = messages[position]
                position += 1
                return message
            return await receive()
        return await self.app(scope, replay, send)
