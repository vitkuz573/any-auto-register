"""Tavily 平台插件"""
import random, string
from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registry import register


@register
class TavilyPlatform(BasePlatform):
    name = "tavily"
    display_name = "Tavily"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox", "oauth_browser"]
    supported_oauth_providers = ["google", "github", "linkedin", "microsoft"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _register_browser(self, identity, password: str) -> Account:
        log = getattr(self, "_log_fn", print)
        extra = self.config.extra or {}
        identity_mode = identity.identity_provider

        if identity_mode == "oauth_browser" and self.config.executor_type != "headed":
            raise RuntimeError("Tavily 浏览器 OAuth 仅支持 executor_type=headed，需要在可见浏览器中完成第三方登录")

        if identity_mode == "mailbox" and not identity.has_mailbox:
            raise ValueError("Tavily 浏览器邮箱注册依赖 mailbox provider，请配置临时邮箱或改用 oauth_browser")

        if identity_mode == "mailbox" and self.config.captcha_solver == "local_solver":
            from services.solver_manager import start
            start()

        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码邮件...")
        verify_link_cb = self._build_link_callback(identity, wait_message="等待验证链接邮件...")

        from platforms.tavily.browser_register import TavilyBrowserRegister

        reg = TavilyBrowserRegister(
            captcha=self._make_captcha(key=extra.get("yescaptcha_key", "")) if identity_mode == "mailbox" else None,
            headless=(self.config.executor_type == "headless"),
            proxy=self.config.proxy,
            otp_callback=otp_cb,
            verification_link_callback=verify_link_cb,
            api_key_timeout=int(extra.get("api_key_timeout", 20) or 20),
            oauth_provider=identity.oauth_provider,
            manual_oauth_timeout=int(extra.get("browser_oauth_timeout", extra.get("manual_oauth_timeout", 300)) or 300),
            chrome_user_data_dir=identity.chrome_user_data_dir,
            chrome_cdp_url=identity.chrome_cdp_url,
            log_fn=log,
        )
        result = reg.register(
            email=identity.email,
            password=password,
            identity_provider=identity_mode,
        )
        return Account(
            platform="tavily",
            email=result["email"],
            password=result["password"],
            status=AccountStatus.REGISTERED,
            extra={"api_key": result["api_key"]},
        )

    def register(self, email: str, password: str = None) -> Account:
        if not password:
            password = "".join(random.choices(string.ascii_letters + string.digits + "!@#", k=14))
        log = getattr(self, '_log_fn', print)
        identity = self._resolve_identity(email, require_email=(self.config.extra or {}).get('identity_provider', 'mailbox') != 'oauth_browser')

        if (self.config.executor_type or "") in ("headless", "headed"):
            log(f"使用浏览器模式注册: {identity.email or '(manual oauth)'}")
            return self._register_browser(identity, password)

        if identity.identity_provider != "mailbox":
            raise RuntimeError("Tavily 当前仅浏览器模式支持 oauth_browser，请使用 executor_type=headed")

        log(f"邮箱: {identity.email}")
        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码邮件...")

        captcha = self._make_captcha(key=self.config.extra.get("yescaptcha_key", ""))

        from platforms.tavily.core import TavilyRegister
        with self._make_executor() as ex:
            reg = TavilyRegister(executor=ex, captcha=captcha, log_fn=log)
            result = reg.register(email=identity.email, password=password,
                                  otp_callback=otp_cb)

        return Account(platform="tavily", email=result["email"], password=result["password"],
                       status=AccountStatus.REGISTERED, extra={"api_key": result["api_key"]})

    def check_valid(self, account: Account) -> bool:
        api_key = account.extra.get("api_key", "")
        if not api_key:
            return False
        import requests
        try:
            r = requests.post("https://api.tavily.com/search",
                              json={"api_key": api_key, "query": "test", "max_results": 1},
                              timeout=10)
            return r.status_code != 401
        except Exception:
            return False
