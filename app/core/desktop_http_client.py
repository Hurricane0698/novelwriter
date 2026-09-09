"""Keep desktop IP-network bypasses compatible with the pinned HTTPX 0.28.1.

HTTPX constructs invalid URL patterns for IPv6 CIDRs and matches IPv4 CIDRs
as single hosts. Intercept those environment patterns before URL parsing;
leave proxy selection, TLS settings, pool ownership and domain rules to HTTPX.
"""

from ipaddress import ip_address, ip_network

from openai import DefaultAsyncHttpxClient


class DesktopAsyncHttpxClient(DefaultAsyncHttpxClient):
    def _get_proxy_map(self, proxy, allow_env_proxies):
        # These two private hooks are covered by real routing regressions and
        # intentionally require the exact HTTPX version pinned in pyproject.toml.
        proxy_map = super()._get_proxy_map(proxy, allow_env_proxies)
        self._no_proxy_networks = []
        for pattern, target in tuple(proxy_map.items()):
            if target is not None or not pattern.startswith("all://"):
                continue
            candidate = pattern.removeprefix("all://")
            if candidate.startswith("[") and candidate.endswith("]"):
                candidate = candidate[1:-1]
            if "/" not in candidate:
                continue
            try:
                network = ip_network(candidate, strict=False)
            except ValueError:
                continue
            self._no_proxy_networks.append(network)
            del proxy_map[pattern]
        return proxy_map

    def _transport_for_url(self, url):
        try:
            address = ip_address(url.host)
        except ValueError:
            pass
        else:
            if any(address in network for network in self._no_proxy_networks):
                return self._transport
        return super()._transport_for_url(url)


def desktop_http_client_kwargs(runtime_mode: str) -> dict[str, DesktopAsyncHttpxClient]:
    if runtime_mode == "desktop":
        return {"http_client": DesktopAsyncHttpxClient()}
    return {}
