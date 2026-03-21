"""Grok (x.ai) 平台插件"""
from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registry import register


@register
class GrokPlatform(BasePlatform):
    name = "grok"
    display_name = "Grok"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox", "oauth_browser"]
    supported_oauth_providers = ["google", "apple", "x"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _register_browser(self, identity, password: str) -> Account:
        log = getattr(self, '_log_fn', print)
        extra = self.config.extra or {}
        identity_mode = identity.identity_provider
        if identity_mode == "oauth_browser" and self.config.executor_type != "headed":
            raise RuntimeError("Grok 浏览器 OAuth 仅支持 executor_type=headed")
        if identity_mode == "mailbox" and not identity.has_mailbox:
            raise ValueError("Grok 浏览器邮箱注册依赖 mailbox provider")
        otp_cb = self._build_otp_callback(
            identity,
            wait_message="等待验证码...",
            code_pattern=r'[A-Z0-9]{3}-[A-Z0-9]{3}',
        )
        from platforms.grok.browser_register import GrokBrowserRegister
        reg = GrokBrowserRegister(
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
            platform="grok",
            email=result["email"],
            password=result.get("password", ""),
            status=AccountStatus.REGISTERED,
            extra={"sso": result.get("sso", ""), "sso_rw": result.get("sso_rw", "")},
        )

    def register(self, email: str, password: str = None) -> Account:
        log = getattr(self, '_log_fn', print)
        extra = self.config.extra or {}
        identity = self._resolve_identity(email, require_email=False)

        if (self.config.executor_type or "") in ("headless", "headed"):
            log(f"使用浏览器模式注册: {identity.email or '(oauth)'}")
            return self._register_browser(identity, password or "")

        if identity.identity_provider == "oauth_browser":
            from platforms.grok.browser_oauth import register_with_browser_oauth
            result = register_with_browser_oauth(
                proxy=self.config.proxy,
                oauth_provider=identity.oauth_provider,
                email_hint=identity.email,
                timeout=int(extra.get("browser_oauth_timeout", extra.get("manual_oauth_timeout", 300)) or 300),
                log_fn=log,
                headless=(self.config.executor_type == "headless"),
                chrome_user_data_dir=identity.chrome_user_data_dir,
                chrome_cdp_url=identity.chrome_cdp_url,
            )
            return Account(
                platform="grok",
                email=result["email"],
                password="",
                status=AccountStatus.REGISTERED,
                extra={
                    "sso": result.get("sso", ""),
                    "sso_rw": result.get("sso_rw", ""),
                },
            )

        if not identity.email:
            raise ValueError("Grok 注册流程依赖 mailbox provider，当前未获取到邮箱账号")
        from platforms.grok.core import GrokRegister
        log(f"邮箱: {identity.email}")
        otp_cb = self._build_otp_callback(
            identity,
            wait_message="等待验证码...",
            code_pattern=r'[A-Z0-9]{3}-[A-Z0-9]{3}',
        )

        yescaptcha_key = self.config.extra.get("yescaptcha_key", "")
        reg = GrokRegister(
            yescaptcha_key=yescaptcha_key,
            proxy=self.config.proxy,
            log_fn=log,
        )
        result = reg.register(
            email=identity.email,
            password=password,
            otp_callback=otp_cb,
        )

        return Account(
            platform="grok",
            email=result["email"],
            password=result["password"],
            status=AccountStatus.REGISTERED,
            extra={
                "sso": result["sso"],
                "sso_rw": result["sso_rw"],
                "given_name": result["given_name"],
                "family_name": result["family_name"],
            },
        )

    def check_valid(self, account: Account) -> bool:
        return bool((account.extra or {}).get("sso"))

    def get_platform_actions(self) -> list:
        return []

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        raise NotImplementedError(f"未知操作: {action_id}")
