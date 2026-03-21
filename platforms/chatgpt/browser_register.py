"""ChatGPT 浏览器注册流程（Camoufox）。"""
import re, time
from typing import Callable, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

OPENAI_AUTH = "https://auth.openai.com"
CHATGPT_APP = "https://chatgpt.com"


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


def _get_cookies(page) -> dict:
    return {c["name"]: c["value"] for c in page.context.cookies()}


def _wait_for_access_token(page, timeout: int = 60) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = page.evaluate("""
            async () => {
                const r = await fetch('/api/auth/session');
                const j = await r.json();
                return j.accessToken || '';
            }
            """)
            if r:
                return r
        except Exception:
            pass
        time.sleep(2)
    return ""


class ChatGPTBrowserRegister:
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
            ob.goto(f"{CHATGPT_APP}/auth/login")
            time.sleep(2)
            if self.oauth_provider:
                try_click_provider_on_page(ob.active_page(), self.oauth_provider)
            if self.chrome_user_data_dir or self.chrome_cdp_url:
                ob.auto_select_google_account()
            else:
                self.log(f"请在浏览器中完成登录，可使用 {browser_login_method_text(self.oauth_provider)}，最长等待 {self.manual_oauth_timeout} 秒")
            if not _wait_for_url(ob.active_page(), "chatgpt.com", timeout=self.manual_oauth_timeout):
                raise RuntimeError(f"ChatGPT 浏览器登录未在 {self.manual_oauth_timeout} 秒内完成")
            page = ob.active_page()
            time.sleep(3)
            access_token = _wait_for_access_token(page, timeout=30)
            cookies = _get_cookies(page)
            resolved = finalize_oauth_email(email, email, "ChatGPT")
            return {
                "email": resolved, "password": password,
                "access_token": access_token,
                "refresh_token": "", "id_token": "",
                "session_token": cookies.get("__Secure-next-auth.session-token", ""),
                "workspace_id": "", "cookies": "",
                "profile": {},
            }

    def register(self, email: str, password: str, identity_provider: str = "mailbox") -> dict:
        if identity_provider in ("oauth_browser", "oauth_manual"):
            return self._register_oauth(email, password)

        proxy = _build_proxy_config(self.proxy)
        launch_opts = {"headless": self.headless}
        if proxy:
            launch_opts["proxy"] = proxy

        with Camoufox(**launch_opts) as browser:
            page = browser.new_page()
            self.log("打开 ChatGPT 注册页")
            page.goto(f"{CHATGPT_APP}/auth/login", wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # Click Sign up
            for sel in ['a[href*="sign-up"]', 'button:has-text("Sign up")', 'a:has-text("Sign up")']:
                if page.query_selector(sel):
                    page.click(sel)
                    time.sleep(3)
                    break

            # Fill email
            email_sel = 'input[name="email"], input[type="email"]'
            try:
                page.wait_for_selector(email_sel, timeout=15000)
            except Exception:
                raise RuntimeError(f"未找到邮箱输入框: {page.url}")
            page.fill(email_sel, email)

            btn = 'button[type="submit"]'
            if page.query_selector(btn):
                page.click(btn)
            time.sleep(3)

            # Password step
            pwd_sel = 'input[name="password"], input[type="password"]'
            try:
                page.wait_for_selector(pwd_sel, timeout=15000)
            except Exception:
                pass
            if page.query_selector(pwd_sel):
                page.fill(pwd_sel, password)
                if page.query_selector(btn):
                    page.click(btn)
                time.sleep(3)

            # OTP step
            otp_sel = 'input[name="code"], input[placeholder*="code"], input[placeholder*="Code"]'
            try:
                page.wait_for_selector(otp_sel, timeout=25000)
            except Exception:
                raise RuntimeError(f"未进入验证码页面: {page.url}")

            if not self.otp_callback:
                raise RuntimeError("ChatGPT 注册需要邮箱验证码但未提供 otp_callback")
            self.log("等待 ChatGPT 验证码")
            code = self.otp_callback()
            if not code:
                raise RuntimeError("未获取到验证码")
            page.fill(otp_sel, code)
            if page.query_selector(btn):
                page.click(btn)
            time.sleep(5)

            # Check for about-you page
            self.log("等待可能的 Name/Birthday 填写步骤...")
            for _ in range(15):
                if "chatgpt.com" in page.url:
                    break
                if page.query_selector('input[name="name"]'):
                    self.log("检测到关于您页面，填写姓名和生日")
                    import random, string
                    first = ''.join(random.choices(string.ascii_lowercase, k=6)).capitalize()
                    last = ''.join(random.choices(string.ascii_lowercase, k=6)).capitalize()
                    page.fill('input[name="name"]', f"{first} {last}")
                    
                    # Fill birthday (React Aria DateField)
                    if page.query_selector('div[data-type="month"]'):
                        page.click('div[data-type="month"]', force=True)
                        page.keyboard.type("01")
                        time.sleep(0.5)
                        page.click('div[data-type="day"]', force=True)
                        page.keyboard.type("01")
                        time.sleep(0.5)
                        page.click('div[data-type="year"]', force=True)
                        page.keyboard.type("1990")
                    
                    time.sleep(1)
                    submit_btn = 'button[type="submit"], button:has-text("Finish")'
                    if page.query_selector(submit_btn):
                        page.click(submit_btn)
                    time.sleep(5)
                    break
                time.sleep(1)

            # Wait for chatgpt.com
            try:
                page.wait_for_url("**/chatgpt.com**", timeout=45000)
            except Exception:
                if not _wait_for_url(page, "chatgpt.com", timeout=15):
                    self.log("未跳转到应用，保存截图到 /tmp/chatgpt_fail.png")
                    page.screenshot(path="/tmp/chatgpt_fail.png")
                    with open("/tmp/chatgpt_fail.html", "w") as f:
                        f.write(page.content())
                    raise RuntimeError(f"ChatGPT 注册后未跳转到应用: {page.url}")

            time.sleep(3)
            # Find and click Skip if onboarding popup appears
            skip_btn = 'button:has-text("Skip")'
            if page.query_selector(skip_btn):
                self.log("点击 Skip 跳过引导")
                try:
                    page.click(skip_btn, timeout=5000)
                except Exception:
                    pass
            time.sleep(3)

            time.sleep(3)
            access_token = _wait_for_access_token(page, timeout=30)
            cookies_dict = _get_cookies(page)
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
            self.log(f"注册成功: {email}")
            return {
                "email": email, "password": password,
                "access_token": access_token,
                "refresh_token": "", "id_token": "",
                "session_token": cookies_dict.get("__Secure-next-auth.session-token", ""),
                "workspace_id": "", "cookies": cookie_str,
                "profile": {},
            }
