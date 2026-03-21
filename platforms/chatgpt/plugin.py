"""ChatGPT / Codex CLI 平台插件"""
import random, string
from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registry import register


@register
class ChatGPTPlatform(BasePlatform):
    name = "chatgpt"
    display_name = "ChatGPT"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox", "oauth_browser"]
    supported_oauth_providers = ["google", "microsoft", "apple"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def check_valid(self, account: Account) -> bool:
        try:
            from platforms.chatgpt.payment import check_subscription_status
            class _A: pass
            a = _A()
            extra = account.extra or {}
            a.access_token = extra.get("access_token") or account.token
            a.cookies = extra.get("cookies", "")
            status = check_subscription_status(a, proxy=self.config.proxy if self.config else None)
            return status not in ("expired", "invalid", "banned", None)
        except Exception:
            return False

    def _make_email_service(self, identity):
        provider = (self.config.extra or {}).get("mail_provider", "tempmail_lol")
        mailbox = getattr(self, "mailbox", None)
        mail_acct = getattr(identity, "mailbox_account", None)
        if not mailbox or not mail_acct:
            raise ValueError("ChatGPT 注册流程依赖 mailbox provider，当前未获取到邮箱账号")

        class MailboxEmailService:
            service_type = type("ST", (), {"value": provider})()

            def __init__(self):
                self._acct = None

            def create_email(self, config=None):
                self._acct = mail_acct
                return {
                    "email": mail_acct.email,
                    "service_id": getattr(mail_acct, "account_id", ""),
                    "token": getattr(mail_acct, "account_id", ""),
                }

            def get_verification_code(self, email=None, email_id=None, timeout=120, pattern=None, otp_sent_at=None):
                acct = self._acct or mail_acct
                return mailbox.wait_for_code(acct, keyword="", timeout=timeout, code_pattern=pattern)

            def update_status(self, success, error=None):
                return None

            @property
            def status(self):
                return None

        return MailboxEmailService()

    def _register_browser(self, identity, password: str) -> Account:
        log = getattr(self, '_log_fn', print)
        extra = self.config.extra or {}
        identity_mode = identity.identity_provider
        if identity_mode == "oauth_browser" and self.config.executor_type != "headed":
            raise RuntimeError("ChatGPT 浏览器 OAuth 仅支持 executor_type=headed")
        if identity_mode == "mailbox" and not identity.has_mailbox:
            raise ValueError("ChatGPT 浏览器邮箱注册依赖 mailbox provider")
        otp_cb = self._build_otp_callback(identity, wait_message="等待验证码...")
        from platforms.chatgpt.browser_register import ChatGPTBrowserRegister
        reg = ChatGPTBrowserRegister(
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
            platform='chatgpt',
            email=result["email"],
            password=result.get("password", ""),
            token=result.get("access_token", ""),
            status=AccountStatus.REGISTERED,
            extra={
                'access_token': result.get("access_token", ""),
                'refresh_token': result.get("refresh_token", ""),
                'id_token': result.get("id_token", ""),
                'session_token': result.get("session_token", ""),
                'workspace_id': result.get("workspace_id", ""),
                'cookies': result.get("cookies", ""),
                'profile': result.get("profile", {}),
            },
        )

    def register(self, email: str = None, password: str = None) -> Account:
        if not password:
            password = "".join(random.choices(
                string.ascii_letters + string.digits + "!@#$", k=16))

        proxy = self.config.proxy if self.config else None
        log_fn = getattr(self, '_log_fn', print)
        extra = self.config.extra or {}
        identity = self._resolve_identity(email, require_email=False)

        if (self.config.executor_type or "") in ("headless", "headed"):
            log_fn(f"使用浏览器模式注册: {identity.email or '(oauth)'}")
            return self._register_browser(identity, password)

        if identity.identity_provider == "oauth_browser":
            from platforms.chatgpt.browser_oauth import register_with_browser_oauth
            result = register_with_browser_oauth(
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
                platform='chatgpt',
                email=result["email"],
                password="",
                user_id=result.get("account_id", ""),
                token=result.get("access_token", ""),
                status=AccountStatus.REGISTERED,
                extra={
                    'access_token': result.get("access_token", ""),
                    'refresh_token': result.get("refresh_token", ""),
                    'id_token': result.get("id_token", ""),
                    'session_token': result.get("session_token", ""),
                    'workspace_id': result.get("workspace_id", ""),
                    'cookies': result.get("cookies", ""),
                    'profile': result.get("profile", {}),
                },
            )

        if not identity.email:
            raise ValueError("ChatGPT 注册流程依赖 mailbox provider，当前未获取到邮箱账号")
        log_fn(f"邮箱: {identity.email}")

        from platforms.chatgpt.register import RegistrationEngine
        engine = RegistrationEngine(
            email_service=self._make_email_service(identity),
            proxy_url=proxy,
            callback_logger=log_fn,
        )
        engine.email = identity.email
        engine.password = password

        result = engine.run()
        if not result or not result.success:
            raise RuntimeError(result.error_message if result else '注册失败')

        return Account(
            platform='chatgpt',
            email=result.email,
            password=result.password or password,
            user_id=result.account_id,
            token=result.access_token,
            status=AccountStatus.REGISTERED,
            extra={
                'access_token':  result.access_token,
                'refresh_token': result.refresh_token,
                'id_token':      result.id_token,
                'session_token': result.session_token,
                'workspace_id':  result.workspace_id,
            },
        )

    def get_platform_actions(self) -> list:
        return [
            {"id": "refresh_token", "label": "刷新 Token", "params": []},
            {"id": "payment_link", "label": "生成支付链接",
             "params": [
                 {"key": "country", "label": "地区", "type": "select",
                  "options": ["US","SG","TR","HK","JP","GB","AU","CA"]},
                 {"key": "plan", "label": "套餐", "type": "select",
                  "options": ["plus", "team"]},
             ]},
            {"id": "upload_cpa", "label": "上传 CPA",
             "params": [
                 {"key": "api_url", "label": "CPA API URL", "type": "text"},
                 {"key": "api_key", "label": "CPA API Key", "type": "text"},
             ]},
            {"id": "upload_tm", "label": "上传 Team Manager",
             "params": [
                 {"key": "api_url", "label": "TM API URL", "type": "text"},
                 {"key": "api_key", "label": "TM API Key", "type": "text"},
             ]},
        ]

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        proxy = self.config.proxy if self.config else None
        extra = account.extra or {}

        class _A: pass
        a = _A()
        a.email = account.email
        a.access_token = extra.get("access_token") or account.token
        a.refresh_token = extra.get("refresh_token", "")
        a.id_token = extra.get("id_token", "")
        a.session_token = extra.get("session_token", "")
        a.client_id = extra.get("client_id", "app_EMoamEEZ73f0CkXaXp7hrann")
        a.cookies = extra.get("cookies", "")

        if action_id == "refresh_token":
            from platforms.chatgpt.token_refresh import TokenRefreshManager
            manager = TokenRefreshManager(proxy_url=proxy)
            result = manager.refresh_account(a)
            if result.success:
                return {"ok": True, "data": {"access_token": result.access_token,
                        "refresh_token": result.refresh_token}}
            return {"ok": False, "error": result.error_message}

        elif action_id == "payment_link":
            from platforms.chatgpt.payment import generate_plus_link, generate_team_link, open_url_incognito
            plan = params.get("plan", "plus")
            country = params.get("country", "US")
            
            # 手动拼凑基础 cookie，以防历史老账号没有保存完整的 cookie 字符串
            if not a.cookies and a.session_token:
                a.cookies = f"__Secure-next-auth.session-token={a.session_token}"
                
            if plan == "plus":
                url = generate_plus_link(a, proxy=proxy, country=country)
            else:
                url = generate_team_link(a, proxy=proxy, country=country)
            
            # 使用本地指纹浏览器无痕挂载 Cookie 强制打开支付页面（防止直接在自己浏览器被踢出登录）
            if url and a.cookies:
                open_url_incognito(url, a.cookies)
                
            return {"ok": bool(url), "data": {"url": url, "message": "支付链接已生成，正在启动带凭证的独立无痕浏览器..."}}

        elif action_id == "upload_cpa":
            from platforms.chatgpt.cpa_upload import upload_to_cpa, generate_token_json
            token_data = generate_token_json(a)
            ok, msg = upload_to_cpa(token_data, api_url=params.get("api_url"),
                                    api_key=params.get("api_key"))
            return {"ok": ok, "data": msg}

        elif action_id == "upload_tm":
            from platforms.chatgpt.cpa_upload import upload_to_team_manager
            ok, msg = upload_to_team_manager(a, api_url=params.get("api_url"),
                                             api_key=params.get("api_key"))
            return {"ok": ok, "data": msg}

        raise NotImplementedError(f"未知操作: {action_id}")
