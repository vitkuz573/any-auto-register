"""OpenBlockLabs 浏览器注册流程（Camoufox）。"""
import random, string, time
from typing import Callable, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

AUTH_BASE = "https://auth.openblocklabs.com"
DASHBOARD = "https://dashboard.openblocklabs.com"


def _build_proxy_config(proxy: Optional[str]) -> Optional[dict]:
    if not proxy:
        return None
    parsed = urlparse(proxy)
    if not parsed.scheme or not parsed.hostname or not parsed.port:
        return {"server": proxy}
    config = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password
    return config


def _wait_for_url(page, substring: str, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if substring in page.url:
            return True
        time.sleep(1)
    return False


def _get_wos_session(page, timeout: int = 60) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for c in page.context.cookies():
            if c["name"] == "wos-session":
                return c["value"]
        time.sleep(1)
    return ""


class OpenBlockLabsBrowserRegister:
    def __init__(
        self,
        *,
        headless: bool,
        proxy: Optional[str] = None,
        otp_callback: Optional[Callable[[], str]] = None,
        oauth_provider: str = "",
        manual_oauth_timeout: int = 300,
        chrome_user_data_dir: str = "",
        chrome_cdp_url: str = "",
        log_fn: Callable[[str], None] = print,
    ):
        self.headless = headless
        self.proxy = proxy
        self.otp_callback = otp_callback
        self.oauth_provider = oauth_provider
        self.manual_oauth_timeout = manual_oauth_timeout
        self.chrome_user_data_dir = chrome_user_data_dir
        self.chrome_cdp_url = chrome_cdp_url
        self.log = log_fn

    def _register_oauth(self, email: str, password: str) -> dict:
        from core.oauth_browser import OAuthBrowser, browser_login_method_text, finalize_oauth_email
        from core.oauth_browser import try_click_provider_on_page
        with OAuthBrowser(
            proxy=self.proxy, headless=False,
            chrome_user_data_dir=self.chrome_user_data_dir,
            chrome_cdp_url=self.chrome_cdp_url, log_fn=self.log,
        ) as ob:
            ob.goto(f"{DASHBOARD}/login")
            time.sleep(2)
            if self.oauth_provider:
                try_click_provider_on_page(ob.active_page(), self.oauth_provider)
            if self.chrome_user_data_dir or self.chrome_cdp_url:
                ob.auto_select_google_account()
            else:
                self.log(f"请在浏览器中完成登录，可使用 {browser_login_method_text(self.oauth_provider)}，最长等待 {self.manual_oauth_timeout} 秒")
            if not _wait_for_url(ob.active_page(), "dashboard.openblocklabs.com", timeout=self.manual_oauth_timeout):
                raise RuntimeError(f"OpenBlockLabs 浏览器登录未在 {self.manual_oauth_timeout} 秒内完成")
            wos = _get_wos_session(ob.active_page(), timeout=15)
            resolved = finalize_oauth_email(email, email, "OpenBlockLabs")
            return {"email": resolved, "password": password, "wos_session": wos}

    def register(self, email: str, password: str, identity_provider: str = "mailbox") -> dict:
        if identity_provider in ("oauth_browser", "oauth_manual"):
            return self._register_oauth(email, password)

        proxy = _build_proxy_config(self.proxy)
        launch_opts = {"headless": self.headless}
        if proxy:
            launch_opts["proxy"] = proxy

        first_name = ''.join(random.choices(string.ascii_lowercase, k=5)).capitalize()
        last_name = ''.join(random.choices(string.ascii_lowercase, k=5)).capitalize()

        with Camoufox(**launch_opts) as browser:
            page = browser.new_page()
            self.log("打开 OpenBlockLabs 注册页")
            page.goto(
                f"{AUTH_BASE}/sign-up?redirect_uri={DASHBOARD}/auth/callback",
                wait_until="networkidle", timeout=30000,
            )
            time.sleep(2)

            # Fill first/last name
            for sel, val in [
                ('input[name="first_name"], input[placeholder*="First"]', first_name),
                ('input[name="last_name"], input[placeholder*="Last"]', last_name),
            ]:
                if page.query_selector(sel):
                    page.fill(sel, val)

            # Fill email
            email_sel = 'input[name="email"], input[type="email"]'
            page.wait_for_selector(email_sel, timeout=15000)
            page.fill(email_sel, email)

            pwd_sel = 'input[name="password"], input[type="password"]'
            btn_sel = 'button[type="submit"], button:has-text("Continue")'

            # 首次提交 (有些表单 Email/PWD 在同一页)
            try:
                if page.query_selector(pwd_sel):
                    page.fill(pwd_sel, password)
            except Exception as e:
                self.log(f"第一页填密码异常: {e}")

            try:
                if page.query_selector(btn_sel):
                    page.click(btn_sel)
            except Exception as e:
                self.log(f"第一页点按异常: {e}")
            time.sleep(3)

            # 如果单独跳到了独立输入密码的页面（或者刚才没填上）
            try:
                page.wait_for_selector(pwd_sel, timeout=8000)
                if "password" in page.url or page.query_selector(pwd_sel):
                    # 重新强制填入并尝试点击
                    page.fill(pwd_sel, password, force=True)
                    time.sleep(1)
                    if page.query_selector(btn_sel):
                        page.click(btn_sel, force=True)
                    time.sleep(3)
            except Exception as e:
                self.log(f"第二步密码填写异常(可能不存在): {e}")

            # OTP / email verification
            # OTP / email verification
            try:
                page.wait_for_url("**/email-verification**", timeout=20000)
            except Exception:
                raise RuntimeError(f"未进入验证码页面: {page.url}")

            if not self.otp_callback:
                raise RuntimeError("OpenBlockLabs 注册需要邮箱验证码但未提供 otp_callback")
            self.log("等待 OpenBlockLabs 验证码")
            code = self.otp_callback()
            if not code:
                raise RuntimeError("未获取到验证码")
            code = code.replace("-", "")
            
            # Debug info
            page.screenshot(path="/tmp/openblocks_otp.png")
            with open("/tmp/openblocks_otp.html", "w") as f:
                f.write(page.content())

            # Find visible input to click and type
            try:
                visible_inputs = page.query_selector_all('input[autocomplete="one-time-code"], input:not([type="hidden"])')
                for vi in visible_inputs:
                    if vi.is_visible() and vi.get_attribute("type") != "email" and vi.get_attribute("type") != "password":
                        vi.click()
                        break
                page.keyboard.type(code)
            except Exception as e:
                self.log(f"填写验证码失败: {e}")
                
            btn = 'button[type="submit"]'
            if page.query_selector(btn):
                page.click(btn)
            time.sleep(5)

            # Wait for dashboard
            if not _wait_for_url(page, "dashboard.openblocklabs.com", timeout=60):
                self.log("未跳转到 dashboard，保存截图到 /tmp/openblocks_fail.png")
                page.screenshot(path="/tmp/openblocks_fail.png")
                with open("/tmp/openblocks_fail.html", "w") as f:
                    f.write(page.content())
                raise RuntimeError(f"OpenBlockLabs 注册后未跳转到 dashboard: {page.url}")

            wos = _get_wos_session(page, timeout=15)
            if not wos:
                self.log("未获取到 wos_session，保存截图到 /tmp/openblocks_fail.png")
                page.screenshot(path="/tmp/openblocks_fail.png")
                with open("/tmp/openblocks_fail.html", "w") as f:
                    f.write(page.content())
                raise RuntimeError("未获取到 wos-session cookie")
            self.log(f"注册成功: {email}")
            return {"email": email, "password": password, "wos_session": wos}
