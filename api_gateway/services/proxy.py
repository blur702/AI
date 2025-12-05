from typing import Any, Dict, Optional, Tuple

import httpx

from ..utils.exceptions import ServiceUnavailableError


class ServiceProxy:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient()

    async def forward_request(
        self,
        service_url: str,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        timeout: int = 300,
    ) -> Tuple[int, Dict[str, Any], bytes]:
        url = service_url.rstrip("/") + "/" + path.lstrip("/")
        hop_by_hop = {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }
        filtered_headers = {
            k: v for k, v in headers.items() if k.lower() not in hop_by_hop
        }

        try:
            response = await self.client.request(
                method=method,
                url=url,
                headers=filtered_headers,
                content=body,
                timeout=timeout,
            )
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(
                f"Error forwarding request to {service_url}: {exc}"
            ) from exc

        resp_headers = dict(response.headers)
        return response.status_code, resp_headers, response.content

