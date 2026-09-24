
import httpx
from fastapi import Request, Response


class ReverseProxy:
    """
    Async reverse proxy using httpx.
    Forwards requests to upstream services with user context headers.
    """

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def forward(
        self,
        request: Request,
        upstream_url: str,
        user_id: str | None = None,
        user_email: str | None = None,
        user_roles: list[str] | None = None,
    ) -> Response:
        # Build upstream URL
        path = request.url.path
        query = str(request.url.query)
        url = f"{upstream_url}{path}"
        if query:
            url += f"?{query}"

        # Forward headers, inject user context
        headers = dict(request.headers)
        headers.pop("host", None)

        if user_id:
            headers["X-User-Id"] = user_id
        if user_email:
            headers["X-User-Email"] = user_email
        if user_roles:
            headers["X-User-Roles"] = ",".join(user_roles)

        # Forward the request
        body = await request.body()
        response = await self.client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
        )

        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )

    async def health_check(self, upstream_url: str) -> bool:
        """Check if an upstream service is healthy."""
        try:
            resp = await self.client.get(f"{upstream_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()