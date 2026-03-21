"""Kiro 平台插件 - 基于 AWS Builder ID 注册"""
from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registry import register


@register
class KiroPlatform(BasePlatform):
    name = "kiro"
    display_name = "Kiro (AWS Builder ID)"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox", "oauth_browser"]
    supported_oauth_providers = ["google", "github", "builderid"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _register_browser(self, identity, password: str) -> Account:
        log = getattr(self, '_log_fn', print)
        extra = self.config.extra or {}
        identity_mode = identity.identity_provider
        if identity_mode == "oauth_browser" and self.config.executor_type != "headed":
            raise RuntimeError("Kiro 浏览器 OAuth 仅支持 executor_type=headed")
        if identity_mode == "mailbox" and not identity.has_mailbox:
            raise ValueError("Kiro 浏览器邮箱注册依赖 mailbox provider")
        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码...")
        from platforms.kiro.browser_register import KiroBrowserRegister
        reg = KiroBrowserRegister(
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
            platform="kiro",
            email=result["email"],
            password=result.get("password", ""),
            token=result.get("accessToken", ""),
            status=AccountStatus.REGISTERED,
            extra={
                "accessToken": result.get("accessToken", ""),
                "refreshToken": result.get("refreshToken", ""),
                "sessionToken": result.get("sessionToken", ""),
                "clientId": result.get("clientId", ""),
                "clientSecret": result.get("clientSecret", ""),
            },
        )

    def register(self, email: str, password: str = None) -> Account:
        proxy = self.config.proxy
        laoudo_account_id = self.config.extra.get("laoudo_account_id", "")
        extra = self.config.extra or {}

        log_fn = getattr(self, '_log_fn', print)
        otp_timeout = int(self.config.extra.get("otp_timeout", 120))
        identity = self._resolve_identity(email, require_email=False)

        if (self.config.executor_type or "") in ("headless", "headed"):
            log_fn(f"使用浏览器模式注册: {identity.email or '(oauth)'}")
            return self._register_browser(identity, password or "")

        if identity.identity_provider == "oauth_browser":
            from platforms.kiro.browser_oauth import register_with_browser_oauth
            info = register_with_browser_oauth(
                proxy=proxy,
                oauth_provider=identity.oauth_provider,
                email_hint=identity.email,
                timeout=int(extra.get("browser_oauth_timeout", extra.get("manual_oauth_timeout", 300)) or 300),
                log_fn=log_fn,
                headless=(self.config.executor_type == "headless"),
                chrome_user_data_dir=identity.chrome_user_data_dir,
                chrome_cdp_url=identity.chrome_cdp_url,
            )
            return Account(
                platform="kiro",
                email=info["email"],
                password="",
                token=info.get("accessToken", ""),
                status=AccountStatus.REGISTERED,
                extra={
                    "name": info.get("name", ""),
                    "accessToken": info.get("accessToken", ""),
                    "sessionToken": info.get("sessionToken", ""),
                    "csrfToken": info.get("csrfToken", ""),
                    "oauthProvider": identity.oauth_provider,
                    "clientId": info.get("clientId", ""),
                    "clientSecret": info.get("clientSecret", ""),
                    "refreshToken": info.get("refreshToken", ""),
                },
            )

        if not identity.email:
            raise ValueError("Kiro 注册流程依赖 mailbox provider，当前未获取到邮箱账号")
        from platforms.kiro.core import KiroRegister
        reg = KiroRegister(proxy=proxy, tag="KIRO")
        reg.log = lambda msg: log_fn(msg)
        log_fn(f"邮箱: {identity.email}")
        otp_cb = self._build_otp_callback(
            identity,
            timeout=otp_timeout,
            wait_message="等待验证码...",
        )

        ok, info = reg.register(
            email=identity.email,
            pwd=password,
            name=self.config.extra.get("name", "Kiro User"),
            mail_token=laoudo_account_id or None,
            otp_timeout=otp_timeout,
            otp_callback=otp_cb,
        )

        if not ok:
            raise RuntimeError(f"Kiro 注册失败: {info.get('error')}")

        return Account(
            platform="kiro",
            email=info["email"],
            password=info["password"],
            status=AccountStatus.REGISTERED,
            extra={
                "name": info.get("name", ""),
                "accessToken": info.get("accessToken", ""),
                "sessionToken": info.get("sessionToken", ""),
                "clientId": info.get("clientId", ""),
                "clientSecret": info.get("clientSecret", ""),
                "refreshToken": info.get("refreshToken", ""),
            },
        )

    def check_valid(self, account: Account) -> bool:
        """通过 refreshToken 检测账号是否有效"""
        extra = account.extra or {}
        refresh_token = extra.get("refreshToken", "")
        if not refresh_token:
            return bool(extra.get("accessToken", "") or account.token)
        try:
            from platforms.kiro.switch import refresh_kiro_token
            ok, _ = refresh_kiro_token(
                refresh_token,
                extra.get("clientId", ""),
                extra.get("clientSecret", ""),
            )
            return ok
        except Exception:
            return False

    def get_platform_actions(self) -> list:
        return [
            {"id": "switch_account", "label": "切换到桌面应用", "params": []},
            {"id": "refresh_token", "label": "刷新 Token", "params": []},
        ]

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        extra = account.extra or {}

        if action_id == "switch_account":
            from platforms.kiro.switch import (
                refresh_kiro_token, switch_kiro_account, restart_kiro_ide,
            )

            access_token = extra.get("accessToken", "") or account.token
            refresh_token = extra.get("refreshToken", "")
            client_id = extra.get("clientId", "")
            client_secret = extra.get("clientSecret", "")
            oauth_provider = (extra.get("oauthProvider", "") or "").strip().lower()

            if refresh_token and client_id and client_secret:
                ok, result = refresh_kiro_token(refresh_token, client_id, client_secret)
                if ok:
                    access_token = result["accessToken"]
                    refresh_token = result.get("refreshToken", refresh_token)

            switch_kwargs = {}
            if oauth_provider in ("google", "github"):
                switch_kwargs["auth_method"] = "social"
                switch_kwargs["provider"] = "Google" if oauth_provider == "google" else "GitHub"

            ok, msg = switch_kiro_account(
                access_token=access_token,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                **switch_kwargs,
            )
            if not ok:
                return {"ok": False, "error": msg}

            restart_ok, restart_msg = restart_kiro_ide()
            return {"ok": True, "data": {
                "message": f"{msg}。{restart_msg}" if restart_ok else msg,
            }}

        elif action_id == "refresh_token":
            from platforms.kiro.switch import refresh_kiro_token

            refresh_token = extra.get("refreshToken", "")
            client_id = extra.get("clientId", "")
            client_secret = extra.get("clientSecret", "")

            ok, result = refresh_kiro_token(refresh_token, client_id, client_secret)
            if ok:
                new_access = result["accessToken"]
                new_refresh = result.get("refreshToken", refresh_token)
                return {
                    "ok": True,
                    "data": {
                        "access_token": new_access,
                        "accessToken": new_access,
                        "refreshToken": new_refresh,
                    },
                }
            return {"ok": False, "error": result.get("error", "刷新失败")}

        raise NotImplementedError(f"未知操作: {action_id}")
