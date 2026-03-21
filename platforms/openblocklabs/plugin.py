"""OpenBlockLabs 平台插件"""
import random, string
from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registry import register


@register
class OpenBlockLabsPlatform(BasePlatform):
    name = "openblocklabs"
    display_name = "OpenBlockLabs"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox", "oauth_browser"]
    supported_oauth_providers = ["github"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _register_browser(self, identity, password: str) -> Account:
        log = getattr(self, '_log_fn', print)
        extra = self.config.extra or {}
        identity_mode = identity.identity_provider
        if identity_mode == "oauth_browser" and self.config.executor_type != "headed":
            raise RuntimeError("OpenBlockLabs 浏览器 OAuth 仅支持 executor_type=headed")
        if identity_mode == "mailbox" and not identity.has_mailbox:
            raise ValueError("OpenBlockLabs 浏览器邮箱注册依赖 mailbox provider")
        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码...")
        from platforms.openblocklabs.browser_register import OpenBlockLabsBrowserRegister
        reg = OpenBlockLabsBrowserRegister(
            headless=(self.config.executor_type == "headless"),
            proxy=self.config.proxy,
            otp_callback=otp_cb,
            oauth_provider=identity.oauth_provider,
            manual_oauth_timeout=int(extra.get("browser_oauth_timeout", extra.get("manual_oauth_timeout", 300)) or 300),
            chrome_user_data_dir=identity.chrome_user_data_dir,
            chrome_cdp_url=identity.chrome_cdp_url,
            log_fn=log,
        )
        result = reg.register(email=identity.email or "", password=password, identity_provider=identity_mode)
        return Account(
            platform="openblocklabs",
            email=result["email"],
            password=result.get("password", ""),
            status=AccountStatus.REGISTERED,
            extra={"wos_session": result.get("wos_session", "")},
            token=result.get("wos_session", ""),
        )

    def register(self, email: str = None, password: str = None) -> Account:
        log = getattr(self, '_log_fn', print)
        proxy = self.config.proxy
        extra = self.config.extra or {}
        identity = self._resolve_identity(email, require_email=False)

        if (self.config.executor_type or "") in ("headless", "headed"):
            log(f"使用浏览器模式注册: {identity.email or '(oauth)'}")
            return self._register_browser(identity, password or "")

        if identity.identity_provider == "oauth_browser":
            from platforms.openblocklabs.browser_oauth import register_with_browser_oauth
            result = register_with_browser_oauth(
                proxy=proxy,
                oauth_provider=identity.oauth_provider,
                email_hint=identity.email,
                timeout=int(extra.get("browser_oauth_timeout", extra.get("manual_oauth_timeout", 300)) or 300),
                log_fn=log,
                headless=(self.config.executor_type == "headless"),
                chrome_user_data_dir=identity.chrome_user_data_dir,
                chrome_cdp_url=identity.chrome_cdp_url,
            )
            return Account(
                platform="openblocklabs",
                email=result["email"],
                password="",
                status=AccountStatus.REGISTERED,
                extra={"wos_session": result.get("wos_session", "")},
                token=result.get("wos_session", ""),
            )

        if not identity.email:
            raise ValueError("OpenBlockLabs 注册流程依赖 mailbox provider，当前未获取到邮箱账号")
        from platforms.openblocklabs.core import OpenBlockLabsRegister
        log(f"邮箱: {identity.email}")
        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码...")

        # 随机姓名
        first_name = "".join(random.choices(string.ascii_lowercase, k=5)).capitalize()
        last_name  = "".join(random.choices(string.ascii_lowercase, k=5)).capitalize()

        reg = OpenBlockLabsRegister(proxy=proxy)
        reg.log = lambda msg: log(msg)

        result = reg.register(
            email=identity.email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            otp_callback=otp_cb,
        )

        if not result.get("success"):
            raise RuntimeError(f"注册失败: {result.get('error')}")

        return Account(
            platform="openblocklabs",
            email=result["email"],
            password=result["password"],
            status=AccountStatus.REGISTERED,
            extra={"wos_session": result.get("wos_session", "")},
            token=result.get("wos_session", ""),
        )

    def check_valid(self, account: Account) -> bool:
        return bool(account.extra.get("wos_session"))
