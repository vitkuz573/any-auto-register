"""Trae.ai 平台插件"""
from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registry import register


@register
class TraePlatform(BasePlatform):
    name = "trae"
    display_name = "Trae.ai"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox", "oauth_browser"]
    supported_oauth_providers = ["google", "github"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _register_browser(self, identity, password: str) -> Account:
        log = getattr(self, '_log_fn', print)
        extra = self.config.extra or {}
        identity_mode = identity.identity_provider
        if identity_mode == "oauth_browser" and self.config.executor_type != "headed":
            raise RuntimeError("Trae 浏览器 OAuth 仅支持 executor_type=headed")
        if identity_mode == "mailbox" and not identity.has_mailbox:
            raise ValueError("Trae 浏览器邮箱注册依赖 mailbox provider")
        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码...")
        from platforms.trae.browser_register import TraeBrowserRegister
        reg = TraeBrowserRegister(
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
            platform="trae",
            email=result["email"],
            password=result.get("password", ""),
            user_id=result.get("user_id", ""),
            token=result.get("token", ""),
            region=result.get("region", ""),
            status=AccountStatus.REGISTERED,
            extra={"cashier_url": result.get("cashier_url", ""), "ai_pay_host": result.get("ai_pay_host", "")},
        )

    def register(self, email: str, password: str = None) -> Account:
        log = getattr(self, '_log_fn', print)
        extra = self.config.extra or {}
        identity = self._resolve_identity(email, require_email=False)

        if (self.config.executor_type or "") in ("headless", "headed"):
            log(f"使用浏览器模式注册: {identity.email or '(oauth)'}")
            return self._register_browser(identity, password or "")

        if identity.identity_provider == "oauth_browser":
            from platforms.trae.browser_oauth import register_with_browser_oauth
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
                platform="trae",
                email=result["email"],
                password="",
                user_id=result.get("user_id", ""),
                token=result["token"],
                region=result.get("region", ""),
                status=AccountStatus.REGISTERED,
                extra={
                    "cashier_url": result.get("cashier_url", ""),
                    "ai_pay_host": result.get("ai_pay_host", ""),
                    "final_url": result.get("final_url", ""),
                },
            )

        if not identity.email:
            raise ValueError("Trae 注册流程依赖 mailbox provider，当前未获取到邮箱账号")
        from platforms.trae.core import TraeRegister
        log(f"邮箱: {identity.email}")
        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码...")

        with self._make_executor() as ex:
            reg = TraeRegister(executor=ex, log_fn=log)
            result = reg.register(
                email=identity.email,
                password=password,
                otp_callback=otp_cb,
            )

        return Account(
            platform="trae",
            email=result["email"],
            password=result["password"],
            user_id=result["user_id"],
            token=result["token"],
            region=result["region"],
            status=AccountStatus.REGISTERED,
            extra={"cashier_url": result["cashier_url"],
                   "ai_pay_host": result["ai_pay_host"]},
        )

    def check_valid(self, account: Account) -> bool:
        return bool(account.token)

    def get_platform_actions(self) -> list:
        """返回平台支持的操作列表"""
        return [
            {"id": "switch_account", "label": "切换到桌面应用", "params": []},
            {"id": "get_user_info", "label": "获取用户信息", "params": []},
            {"id": "get_cashier_url", "label": "获取升级链接", "params": []},
        ]

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        """执行平台操作"""
        if action_id == "switch_account":
            from platforms.trae.switch import switch_trae_account, restart_trae_ide
            
            token = account.token
            user_id = account.user_id or ""
            email = account.email or ""
            region = account.region or ""
            
            if not token:
                return {"ok": False, "error": "账号缺少 token"}
            
            ok, msg = switch_trae_account(token, user_id, email, region)
            if not ok:
                return {"ok": False, "error": msg}
            
            restart_ok, restart_msg = restart_trae_ide()
            return {
                "ok": True,
                "data": {
                    "message": f"{msg}。{restart_msg}" if restart_ok else msg,
                }
            }
        
        elif action_id == "get_user_info":
            from platforms.trae.switch import get_trae_user_info
            
            token = account.token
            if not token:
                return {"ok": False, "error": "账号缺少 token"}
            
            user_info = get_trae_user_info(token)
            if user_info:
                return {"ok": True, "data": user_info}
            return {"ok": False, "error": "获取用户信息失败"}
        
        elif action_id == "get_cashier_url":
            from platforms.trae.core import TraeRegister
            with self._make_executor() as ex:
                reg = TraeRegister(executor=ex)
                # 重新登录刷新 session，再获取新 token 和 cashier_url
                reg.step4_trae_login()
                token = reg.step5_get_token()
                if not token:
                    token = account.token
                cashier_url = reg.step7_create_order(token)
            if not cashier_url:
                return {"ok": False, "error": "获取升级链接失败，token 可能已过期，请重新注册"}
            return {"ok": True, "data": {"cashier_url": cashier_url, "message": "请在浏览器中打开升级链接完成 Pro 订阅"}}

        raise NotImplementedError(f"未知操作: {action_id}")
