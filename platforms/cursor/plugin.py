"""Cursor 平台插件"""
from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registry import register
from platforms.cursor.core import CursorRegister, UA, CURSOR


@register
class CursorPlatform(BasePlatform):
    name = "cursor"
    display_name = "Cursor"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox", "oauth_browser"]
    supported_oauth_providers = ["google", "github"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def register(self, email: str, password: str = None) -> Account:
        log = getattr(self, '_log_fn', print)
        proxy = self.config.proxy
        yescaptcha_key = self.config.extra.get("yescaptcha_key", "")
        extra = self.config.extra or {}

        identity = self._resolve_identity(email, require_email=False)

        # 浏览器模式注册
        if (self.config.executor_type or "") in ("headless", "headed"):
            log(f"使用浏览器模式注册: {identity.email or '(oauth)'}")
            
            # OAuth 模式暂时保留原实现
            if identity.identity_provider == "oauth_browser":
                if self.config.executor_type != "headed":
                    raise RuntimeError("Cursor 浏览器 OAuth 仅支持 executor_type=headed")
                from platforms.cursor.browser_oauth import register_with_browser_oauth
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
                    platform="cursor",
                    email=result["email"],
                    password="",
                    token=result["token"],
                    status=AccountStatus.REGISTERED,
                    extra={"user_info": result.get("user_info", {})},
                )
            
            # 邮箱模式：使用 Camoufox 浏览器注册
            if not identity.email:
                raise ValueError("浏览器模式需要邮箱地址")

            # 构建 captcha solver：优先 local_solver，其次 yescaptcha
            captcha_solver = None
            captcha_type = self.config.captcha_solver or "local_solver"
            if captcha_type == "local_solver":
                from core.base_captcha import LocalSolverCaptcha
                solver_url = self.config.extra.get("solver_url", "http://localhost:8889")
                captcha_solver = LocalSolverCaptcha(solver_url)
            elif captcha_type == "yescaptcha":
                captcha_solver = self._make_captcha()

            # 构建 otp_callback（从 mailbox 获取验证码）
            otp_cb = self._build_otp_callback(
                identity,
                wait_message="等待 Cursor 邮箱验证码...",
                success_label="验证码",
            )

            from platforms.cursor.browser_register import CursorBrowserRegister
            reg = CursorBrowserRegister(
                captcha=captcha_solver,
                headless=(self.config.executor_type == "headless"),
                proxy=proxy,
                otp_callback=otp_cb,
                log_fn=log,
            )
            result = reg.register(email=identity.email, password=password or "")
            return Account(
                platform="cursor",
                email=result["email"],
                password=result.get("password", ""),
                token=result["token"],
                status=AccountStatus.REGISTERED,
            )

        # 协议模式 OAuth
        if identity.identity_provider == "oauth_browser":
            from platforms.cursor.browser_oauth import register_with_browser_oauth
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
                platform="cursor",
                email=result["email"],
                password="",
                token=result["token"],
                status=AccountStatus.REGISTERED,
                extra={"user_info": result.get("user_info", {})},
            )

        # 协议模式邮箱注册
        if not identity.email:
            raise ValueError("Cursor 注册流程依赖 mailbox provider，当前未获取到邮箱账号")
        
        reg = CursorRegister(proxy=proxy, log_fn=log)
        log(f"邮箱: {identity.email}")
        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码...")

        result = reg.register(
            email=identity.email,
            password=password,
            otp_callback=otp_cb,
            yescaptcha_key=yescaptcha_key,
        )

        return Account(
            platform="cursor",
            email=result["email"],
            password=result["password"],
            token=result["token"],
            status=AccountStatus.REGISTERED,
        )

    def check_valid(self, account: Account) -> bool:
        from curl_cffi import requests as curl_req
        try:
            r = curl_req.get(
                f"{CURSOR}/api/auth/me",
                headers={"Cookie": f"WorkosCursorSessionToken={account.token}",
                         "user-agent": UA},
                impersonate="chrome124", timeout=15,
            )
            return r.status_code == 200
        except Exception:
            return False

    def get_platform_actions(self) -> list:
        """返回平台支持的操作列表"""
        return [
            {"id": "switch_account", "label": "切换到桌面应用", "params": []},
            {"id": "get_user_info", "label": "获取用户信息", "params": []},
        ]

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        """执行平台操作"""
        if action_id == "switch_account":
            from platforms.cursor.switch import switch_cursor_account, restart_cursor_ide
            
            token = account.token
            if not token:
                return {"ok": False, "error": "账号缺少 token"}
            
            ok, msg = switch_cursor_account(token)
            if not ok:
                return {"ok": False, "error": msg}
            
            restart_ok, restart_msg = restart_cursor_ide()
            return {
                "ok": True,
                "data": {
                    "message": f"{msg}。{restart_msg}" if restart_ok else msg,
                }
            }
        
        elif action_id == "get_user_info":
            from platforms.cursor.switch import get_cursor_user_info
            
            token = account.token
            if not token:
                return {"ok": False, "error": "账号缺少 token"}
            
            user_info = get_cursor_user_info(token)
            if user_info:
                return {"ok": True, "data": user_info}
            return {"ok": False, "error": "获取用户信息失败"}
        
        raise NotImplementedError(f"未知操作: {action_id}")
