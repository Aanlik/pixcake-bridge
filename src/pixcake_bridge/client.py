import asyncio
import mimetypes
from pathlib import Path

import httpx


class ApiError(Exception):
    def __init__(self, status: int, uncertain=False):
        self.status = status
        self.uncertain = uncertain
        super().__init__(f"PicPeak HTTP {status}" if status else "PicPeak 网络中断")


class PicPeak:
    def __init__(self, url: str, token: str, transport=None):
        self.http = httpx.AsyncClient(base_url=url.rstrip("/") + "/api/v1/", headers={"Authorization": f"Bearer {token}"}, timeout=httpx.Timeout(180, connect=10), transport=transport, follow_redirects=False)

    async def close(self):
        await self.http.aclose()

    async def photos(self, event_id: int):
        photos, page, pages = [], 1, 1
        while page <= pages:
            response = None
            for attempt in range(3):
                try:
                    response = await self.http.get(f"events/{event_id}/photos", params={"page": page, "limit": 100, "mark_source": "client"})
                except httpx.TransportError:
                    if attempt == 2:
                        raise ApiError(0)
                else:
                    if response.status_code < 400:
                        break
                    if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                        raise ApiError(response.status_code)
                delay = min(30, 2 ** attempt)
                if response is not None:
                    try:
                        delay = min(30, max(delay, float(response.headers.get("Retry-After", "0"))))
                    except ValueError:
                        pass
                await asyncio.sleep(delay)
            payload = response.json()
            photos.extend(payload["photos"])
            pages = int(payload["pagination"]["pages"])
            if pages > 10000:
                raise ValueError("PicPeak 分页异常")
            page += 1
        if len({p["id"] for p in photos}) != len(photos):
            raise ValueError("PicPeak 分页期间列表变化，拒绝使用不完整选片快照")
        return photos

    async def replace(self, event_id: int, photo_id: int, file: Path, filename: str):
        # Do not retry a mutation automatically: a lost response may mean the
        # replacement already succeeded. The engine reconciles our marker.
        with file.open("rb") as stream:
            try:
                r = await self.http.post(f"events/{event_id}/photos", data={"replaces_photo_id": str(photo_id)}, files={"photo": (filename, stream, mimetypes.guess_type(filename)[0] or "image/jpeg")})
            except httpx.TransportError:
                raise ApiError(0, uncertain=True)
        if r.status_code >= 400:
            raise ApiError(r.status_code, uncertain=r.status_code >= 500)
        data = r.json()
        if not data.get("replaced") or data.get("photo", {}).get("id") != photo_id:
            raise ApiError(0, uncertain=True)
        return data
