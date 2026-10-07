import httpx
import pytest

from pixcake_bridge.client import ApiError, PicPeak


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 502, 503])
async def test_http_errors(status, monkeypatch):
    async def sleep(_):
        pass
    monkeypatch.setattr("pixcake_bridge.client.asyncio.sleep", sleep)
    client = PicPeak("http://picpeak", "secret", httpx.MockTransport(lambda r: httpx.Response(status)))
    with pytest.raises(ApiError) as e:
        await client.photos(1)
    assert e.value.status == status
    await client.close()


async def test_network_retry(monkeypatch):
    calls = []
    async def sleep(_):
        pass
    monkeypatch.setattr("pixcake_bridge.client.asyncio.sleep", sleep)
    def transport(req):
        calls.append(req)
        raise httpx.ConnectError("offline")
    client = PicPeak("http://picpeak", "secret", httpx.MockTransport(transport))
    with pytest.raises(ApiError):
        await client.photos(1)
    assert len(calls) == 3
    await client.close()


async def test_pagination_uses_client_marks():
    def transport(req):
        assert req.url.params["mark_source"] == "client"
        page = int(req.url.params["page"])
        return httpx.Response(200, json={"photos": [{"id": page}], "pagination": {"pages": 2}})
    client = PicPeak("http://picpeak", "secret", httpx.MockTransport(transport))
    assert await client.photos(1) == [{"id": 1}, {"id": 2}]
    await client.close()


async def test_lost_upload_is_uncertain_and_not_retried(tmp_path):
    calls = []
    def transport(req):
        calls.append(req)
        assert b'replaces_photo_id' in req.read()
        raise httpx.ReadTimeout("response lost")
    file = tmp_path / "a.jpg"
    file.write_bytes(b"jpeg")
    client = PicPeak("http://picpeak", "secret", httpx.MockTransport(transport))
    with pytest.raises(ApiError) as e:
        await client.replace(1, 3, file, "a.jpg")
    assert e.value.uncertain
    assert len(calls) == 1
    await client.close()
