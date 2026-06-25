"""
HTTP 会话工具 — 仅使用 Python 标准库 urllib
提供类似 requests.Session 的 get/post 接口
"""

import urllib.request
import urllib.parse
import http.cookiejar
import ssl


class Response:
    """类似 requests.Response 的包装"""
    __slots__ = ('status_code', 'text', 'headers', 'url')

    def __init__(self, status_code, text, headers, url):
        self.status_code = status_code
        self.text = text
        self.headers = headers
        self.url = url


class Session:
    """类似 requests.Session — 自动管理 Cookie"""

    def __init__(self):
        self.cookiejar = http.cookiejar.CookieJar()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
        }
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def _build_opener(self):
        return urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler(),
            urllib.request.HTTPCookieProcessor(self.cookiejar),
        )

    def _request(self, method, url, data=None, headers=None, timeout=15):
        req_headers = dict(self.headers)
        if headers:
            req_headers.update(headers)

        body = None
        if data is not None:
            body = urllib.parse.urlencode(data).encode('utf-8')
            if 'Content-Type' not in req_headers:
                req_headers['Content-Type'] = 'application/x-www-form-urlencoded'

        req = urllib.request.Request(
            url, data=body, headers=req_headers, method=method
        )

        opener = self._build_opener()
        try:
            resp = opener.open(req, timeout=timeout)
            text = resp.read().decode('utf-8', errors='replace')
            return Response(
                status_code=resp.status,
                text=text,
                headers=dict(resp.headers),
                url=resp.url,
            )
        except urllib.error.HTTPError as e:
            text = e.read().decode('utf-8', errors='replace')
            return Response(
                status_code=e.code,
                text=text,
                headers=dict(e.headers),
                url=e.url if hasattr(e, 'url') else url,
            )
        except urllib.error.URLError as e:
            raise Exception(f'网络错误: {e.reason}') from e

    def get(self, url, cookies=None, timeout=15):
        """GET 请求"""
        hdrs = None
        if cookies:
            cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())
            hdrs = {'Cookie': cookie_str}
        return self._request('GET', url, headers=hdrs, timeout=timeout)

    def post(self, url, data=None, cookies=None, timeout=15, headers=None):
        """POST 请求"""
        hdrs = dict(headers or {})
        if cookies:
            cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())
            hdrs['Cookie'] = cookie_str
        return self._request('POST', url, data=data, headers=hdrs, timeout=timeout)
