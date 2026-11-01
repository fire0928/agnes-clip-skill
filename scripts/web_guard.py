"""本地 HTTP 服务的跨站请求防护（CSRF / DNS rebinding）。

## 为什么需要

本 skill 会起本地服务（世界观编辑台、配音台、成片预览），
监听 127.0.0.1 的某个端口，页面上可以改剧本、存配置、触发合成。

监听 127.0.0.1 **不等于安全**：浏览器里随便打开一个网页，
那个网页可以发 POST 到 `http://127.0.0.1:8777/api/save`，
把你的剧本改掉、或触发一次要花钱的合成 —— 这就是 CSRF。
（GET 不行，但 POST 可以，跨域请求照样发得出去。）

另外还有 DNS rebinding：攻击者把一个域名解析到 127.0.0.1，
浏览器访问 `http://evil.example:8777/` 时，Host 头是 evil.example，
但请求实际打到了你本机。

## 怎么防

对**所有写操作（POST/PUT/DELETE）** 检查两个头：

- `Origin`：存在时必须指向本机（127.0.0.1 / localhost / ::1）；
- `Host`：必须解析到回环地址（挡 DNS rebinding）。

`Origin` 缺失时（比如 curl、Python 脚本）**放行** ——
本地工具调用是正常用法，不能把自动化脚本堵死。
真正的浏览器跨域请求一定会带 Origin，所以这个组合是安全的。

用法：

    from web_guard import check_write_request
    if not check_write_request(self.headers, allowed_ports):
        self._json({"ok": False, "message": "跨站请求已拒绝"}, 403)
        return
"""
import ipaddress
import socket

# 允许的回环主机名
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}


def _is_loopback_host(host):
    """host 是不是本机。"""
    if not host:
        return False
    h = host.strip().lower()
    # 去掉端口
    if h.startswith("["):          # [::1]:8777
        h = h.split("]")[0][1:]
    elif ":" in h:                  # 127.0.0.1:8777
        h = h.split(":")[0]
    if h in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _origin_ok(origin, allowed_ports):
    """Origin 是不是本机。同源比较忽略端口之外的差异。"""
    if not origin:
        return True              # 没有 Origin = 非浏览器调用，放行
    o = origin.strip().lower()
    if o == "null":
        return False             # file:// 之类，一律拒绝
    # 取 host 部分
    if "//" in o:
        o = o.split("//", 1)[1]
    host = o.split("/")[0]
    if not _is_loopback_host(host):
        return False
    # 端口对不上也拒绝（防止别的端口的服务来打这个接口）
    if ":" in host and "]" not in host:
        host, _, port = host.partition(":")
        if port.isdigit() and allowed_ports and int(port) not in allowed_ports:
            return False
    return True


def check_write_request(headers, allowed_ports=None):
    """写操作前的校验。返回 True = 放行，False = 应拒绝（403）。

    headers  : http.client.HTTPMessage 或任何有 .get() 的对象
    allowed_ports : 允许的端口集合（int）。传 None 表示不检查端口。
    """
    get = getattr(headers, "get", None)
    if get is None:
        return True
    origin = get("Origin") or get("origin")
    if not _origin_ok(origin, allowed_ports):
        return False
    host = get("Host") or get("host")
    if host and not _is_loopback_host(host):
        return False
    return True


def resolve_local(host):
    """把 host 解析成 IP，判断是不是回环（挡 DNS rebinding）。"""
    try:
        h = host.strip().lower()
        if h.startswith("["):
            h = h.split("]")[0][1:]
        elif ":" in h:
            h = h.split(":")[0]
        infos = socket.getaddrinfo(h, None)
        for info in infos:
            ip = info[4][0]
            if not ipaddress.ip_address(ip).is_loopback:
                return False
        return True
    except Exception:
        return False
