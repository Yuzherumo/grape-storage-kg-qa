"""国家农业科学数据中心（www.agridata.cn）前端 API 客户端。

站点前端 /frontend/js/request.js 对每个 /api 请求套一层信封：

    POST /api/app/...
    {
      "common": {
        "appId": ..., "timestamp": <毫秒>, "nonce": <6位>,
        "encrypted": false,
        "appToken": md5(appId + aes16 + timestamp + nonce),
        "aes16": RSA_PKCS1v15(aes16, 站点公钥) -> base64
      },
      "json": <业务参数>
    }

服务端回包形如 {"code":0, "encrypted":true, "data":"<AES-128-ECB 密文>"}，
密钥即本次请求的 aes16，因此客户端必须自己持有 aes16 才能解出数据。

本模块只用标准库（urllib + hashlib + 自实现 RSA/AES），见 agridata_crypto.py。
"""
from __future__ import annotations

import hashlib
import json
import random
import ssl
import string
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agridata_crypto import aes_decrypt_b64, rsa_encrypt_pkcs1v15

BASE = "http://www.agridata.cn"
APP_ID = "947bc872d4134a91a0ffaedac05fdb14"
SITE_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC49WMjbNPNK+NIw+H+PJ7oLEzy6b14eYXB1vi17Kc5Qe2J"
    "/bhQsXO9qw+T91fANliBGeMZlnWK56G0KpHxpj40Wi58VGGOo3XfCKWqOGASLXR42ppspdIV9QKzSg4GoilcD"
    "PAlsAOSSbpv3O1ckPSWOzG4QpagaKQpYZpSIFBzCQIDAQAB"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CTX = ssl.create_default_context()
_LOWER = string.ascii_lowercase + string.digits
RAW_DIR = Path(".tmp/agridata/raw")


class ApiError(RuntimeError):
    """接口返回非 0 code。"""

    def __init__(self, path: str, payload: dict[str, Any]) -> None:
        self.path = path
        self.payload = payload
        super().__init__(f"[{path}] code={payload.get('code')} message={payload.get('message')!r}")


def _nonce(length: int, alphabet: str = _LOWER) -> str:
    return "".join(random.choice(alphabet) for _ in range(length))


def build_envelope(payload: Any) -> tuple[dict[str, Any], str]:
    """返回 (信封, aes16)；aes16 用于解服务端回包。"""
    aes16 = _nonce(16)
    ts = str(int(time.time() * 1000))
    non = _nonce(6)
    app_token = hashlib.md5((APP_ID + aes16 + ts + non).encode("utf-8")).hexdigest()
    env = {
        "common": {
            "appId": APP_ID,
            "timestamp": ts,
            "nonce": non,
            "encrypted": False,
            "appToken": app_token,
            "aes16": rsa_encrypt_pkcs1v15(aes16, SITE_PUBLIC_KEY),
        },
        "json": payload,
    }
    return env, aes16


def _post(url: str, body: dict[str, Any], token: str | None = None, timeout: int = 45) -> str:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Origin": BASE,
        "Referer": BASE + "/data/index.html",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read().decode("utf-8", "replace")


def api(path: str, payload: Any, token: str | None = None, timeout: int = 45,
        retries: int = 3, raw_log: bool = False) -> Any:
    """调用 /api 接口，返回已解密的业务数据（dict/list/str）。"""
    path = path if path.startswith("/") else "/" + path
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        env, aes16 = build_envelope(payload)
        try:
            text = _post(BASE + path, env, token=token, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            time.sleep(1.5 * attempt)
            continue
        try:
            outer = json.loads(text)
        except json.JSONDecodeError:
            last_exc = RuntimeError(f"[{path}] 非 JSON 响应: {text[:300]!r}")
            time.sleep(1.5 * attempt)
            continue
        code = outer.get("code")
        if code not in (0, "0"):
            raise ApiError(path, outer)
        data = outer.get("data")
        if outer.get("encrypted"):
            if not isinstance(data, str):
                raise RuntimeError(f"[{path}] encrypted=true 但 data 不是字符串: {type(data)}")
            data = json.loads(aes_decrypt_b64(data, aes16).decode("utf-8"))
            # 站点把 {code, data} 信封整体加密后再 base64 放进外层 data 字段，
            # 解出来仍是信封，需要再剥一层（这是实测行为，不是猜测）。
            if isinstance(data, dict) and "code" in data and "data" in data:
                inner_code = data.get("code")
                if inner_code not in (0, "0"):
                    raise ApiError(path, data)
                data = data.get("data")
        if raw_log:
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%H%M%S")
            safe = path.strip("/").replace("/", "_")
            (RAW_DIR / f"{safe}_{stamp}_{_nonce(4)}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        return data
    raise RuntimeError(f"[{path}] 请求失败（重试 {retries} 次）: {last_exc}") from last_exc


# --------------------------------------------------------------------------
# 业务封装
# --------------------------------------------------------------------------
def search_datasets(keyword: str, page: int = 1, size: int = 20,
                    resource_type: str = "DATASET_INFO",
                    extra_filter: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = {
        "resourceType": resource_type,
        "custom": {"searchText": keyword, "filter": extra_filter or []},
        "pageNumber": page,
        "pageSize": size,
    }
    return api("/api/app/dataset/search/list", payload)


def facet(keyword: str, fields: list[str], size: int = 20) -> dict[str, Any]:
    payload = {
        "resourceType": "DATASET_INFO",
        "custom": {
            "searchText": keyword,
            "filter": [],
            "facetFields": fields,
            "facetSize": size,
        },
        "pageNumber": 1,
        "pageSize": 0,
    }
    return api("/api/app/dataset/search/facet", payload)


def subject_category_tree() -> Any:
    return api("/api/app/subject/category/tree", {})


def special_category_tree(is_home: str = "no", search_word: str = "") -> Any:
    return api("/api/app/special/category/tree", {"isHome": is_home, "searchWord": search_word})


def wiki_by_keyword(keyword: str) -> Any:
    return api("/api/app/special/getWikiByKeyword", {"keyword": keyword})


if __name__ == "__main__":
    res = search_datasets("葡萄", size=5)
    print(json.dumps(res, ensure_ascii=False)[:1500])
