"""Optional MCP apps over Streamable HTTP, with per-Windows-user OAuth storage."""
import asyncio
import http.server
import json
import time
import urllib.parse
import webbrowser
from datetime import timedelta


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
        raise ValueError('Enter an MCP endpoint URL without credentials or a fragment.')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('Use HTTPS, or HTTP on localhost for a local MCP server.')
    return url


class CredentialStore:
    def __init__(self, store, identity):
        self.store, self.key = store, 'mcp:' + identity

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken
        value = self.store.secret(self.key + ':tokens')
        return OAuthToken.model_validate_json(value) if value else None

    async def set_tokens(self, tokens):
        self.store.secret(self.key + ':tokens', tokens.model_dump_json())

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull
        value = self.store.secret(self.key + ':client')
        return OAuthClientInformationFull.model_validate_json(value) if value else None

    async def set_client_info(self, client_info):
        self.store.secret(self.key + ':client', client_info.model_dump_json())


def invoke(store, identity, tool=None, arguments=None, *, connect=False):
    config = next((r for r in store.settings['mcp_connections'] if r['id'] == identity), None)
    if config is None:
        raise ValueError('That app is no longer connected.')
    validate_url(config['url'])
    async def run():
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from mcp.client.auth import OAuthClientProvider
        from mcp.shared.auth import OAuthClientMetadata
        response = {}
        class Callback(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path != '/callback':
                    self.send_error(404)
                    return
                params = urllib.parse.parse_qs(parsed.query)
                response.update({key: value[0] for key, value in params.items()})
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(b'You can return to Notch. The connection is being checked.')
            def log_message(self, *args):
                pass
        server = None
        headers = {}
        auth = None
        try:
            if config.get('auth', 'OAuth') == 'OAuth':
                # Keep a stable registered callback port across token refresh/restarts.
                redirect_uri = 'http://127.0.0.1:11437/callback'
                async def redirect(url):
                    nonlocal server
                    if not connect:
                        raise ValueError('Reconnect this app in Settings → Connections to sign in again.')
                    server = http.server.HTTPServer(('127.0.0.1', 11437), Callback)
                    server.timeout = 1
                    webbrowser.open(url)
                async def callback():
                    deadline = time.monotonic() + 180
                    while not response and time.monotonic() < deadline:
                        await asyncio.to_thread(server.handle_request)
                    if 'code' not in response:
                        raise ValueError('Sign-in was cancelled or timed out.')
                    return response['code'], response.get('state')
                auth = OAuthClientProvider(server_url=config['url'],
                    client_metadata=OAuthClientMetadata(client_name='Notch Snippy', redirect_uris=[redirect_uri],
                        grant_types=['authorization_code', 'refresh_token'], response_types=['code'], token_endpoint_auth_method='none'),
                    storage=CredentialStore(store, identity), redirect_handler=redirect, callback_handler=callback)
            elif config.get('auth') == 'Bearer token':
                headers['Authorization'] = 'Bearer ' + store.secret('mcp:' + identity + ':bearer')
            async with httpx.AsyncClient(auth=auth, headers=headers, timeout=httpx.Timeout(30, read=200 if connect else 60)) as client:
                async with streamable_http_client(config['url'], http_client=client) as (read, write, _):
                    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=210 if connect else 60)) as session:
                        await session.initialize()
                        if tool:
                            result = await session.call_tool(tool, arguments or {})
                            return {'text': '\n'.join(getattr(item, 'text', '[Non-text result]') for item in result.content)[:16000],
                                    'error': bool(result.isError)}
                        result = await session.list_tools()
                        return [row.model_dump() for row in result.tools]
        finally:
            if server:
                server.server_close()
    try:
        return asyncio.run(run())
    except Exception as error:
        # Task-group wrappers obscure useful connection errors. Do not include tokens.
        def first(exc):
            return first(exc.exceptions[0]) if isinstance(exc, BaseExceptionGroup) else exc
        error = first(error)
        if isinstance(error, ValueError):
            raise ValueError(str(error)) from None
        raise ValueError('The MCP app could not complete this request. Check its endpoint and reconnect in Settings → Connections.') from None
