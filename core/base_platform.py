"""平台插件基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import time


class AccountStatus(str, Enum):
    REGISTERED   = "registered"
    TRIAL        = "trial"
    SUBSCRIBED   = "subscribed"
    EXPIRED      = "expired"
    INVALID      = "invalid"


@dataclass
class Account:
    platform: str
    email: str
    password: str
    user_id: str = ""
    region: str = ""
    token: str = ""
    status: AccountStatus = AccountStatus.REGISTERED
    trial_end_time: int = 0       # unix timestamp
    extra: dict = field(default_factory=dict)  # 平台自定义字段
    created_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class RegisterConfig:
    """注册任务配置"""
    executor_type: str = "protocol"   # protocol | headless | headed
    captcha_solver: str = "yescaptcha"  # yescaptcha | 2captcha | manual
    proxy: Optional[str] = None
    extra: dict = field(default_factory=dict)


class BasePlatform(ABC):
    # 子类必须定义
    name: str = ""
    display_name: str = ""
    version: str = "1.0.0"
    # 子类声明支持的执行器类型，未列出的自动降级到 protocol
    supported_executors: list = ["protocol", "headless", "headed"]
    supported_identity_modes: list = ["mailbox"]
    supported_oauth_providers: list = []

    def __init__(self, config: RegisterConfig = None):
        self.config = config or RegisterConfig()
        if self.config.executor_type not in self.supported_executors:
            raise NotImplementedError(
                f"{self.display_name} 暂不支持 '{self.config.executor_type}' 执行器，"
                f"当前支持: {self.supported_executors}"
            )

    @abstractmethod
    def register(self, email: str, password: str = None) -> Account:
        """执行注册流程，返回 Account"""
        ...

    @abstractmethod
    def check_valid(self, account: Account) -> bool:
        """检测账号是否有效"""
        ...

    def get_trial_url(self, account: Account) -> Optional[str]:
        """生成试用激活链接（可选实现）"""
        return None

    def get_platform_actions(self) -> list:
        """
        返回平台支持的额外操作列表，每项格式:
        {"id": str, "label": str, "params": [{"key": str, "label": str, "type": str}]}
        """
        return []

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        """
        执行平台特定操作，返回 {"ok": bool, "data": any, "error": str}
        """
        raise NotImplementedError(f"平台 {self.name} 不支持操作: {action_id}")

    def get_quota(self, account: Account) -> dict:
        """查询账号配额（可选实现）"""
        return {}

    def _make_executor(self):
        """根据 config 创建执行器"""
        from .executors.protocol import ProtocolExecutor
        t = self.config.executor_type
        if t == "protocol":
            return ProtocolExecutor(proxy=self.config.proxy)
        elif t == "headless":
            from .executors.playwright import PlaywrightExecutor
            return PlaywrightExecutor(proxy=self.config.proxy, headless=True)
        elif t == "headed":
            from .executors.playwright import PlaywrightExecutor
            return PlaywrightExecutor(proxy=self.config.proxy, headless=False)
        raise ValueError(f"未知执行器类型: {t}")

    def _make_captcha(self, **kwargs):
        """根据 config 创建验证码解决器"""
        from .base_captcha import YesCaptcha, ManualCaptcha, LocalSolverCaptcha
        t = self.config.captcha_solver
        if t == "yescaptcha":
            key = kwargs.get("key") or self.config.extra.get("yescaptcha_key", "")
            return YesCaptcha(key)
        elif t == "manual":
            return ManualCaptcha()
        elif t == "local_solver":
            url = self.config.extra.get("solver_url", "http://localhost:8889")
            return LocalSolverCaptcha(url)
        raise ValueError(f"未知验证码解决器: {t}")

    def _get_identity_provider_name(self) -> str:
        from .base_identity import normalize_identity_provider
        return normalize_identity_provider(self.config.extra.get("identity_provider", "mailbox"))

    def _get_identity_provider(self):
        from .base_identity import create_identity_provider

        mode = self._get_identity_provider_name()
        if mode not in self.supported_identity_modes:
            raise NotImplementedError(
                f"{self.display_name} 暂不支持 identity_provider='{mode}'，"
                f"当前支持: {self.supported_identity_modes}"
            )
        return create_identity_provider(
            mode,
            mailbox=getattr(self, "mailbox", None),
            extra=self.config.extra,
        )

    def _resolve_identity(self, email: str = None, *, require_email: bool = True):
        identity = self._get_identity_provider().resolve(email)
        if require_email and not identity.email:
            raise ValueError(
                f"{self.display_name} 注册流程未获取到可用邮箱，"
                f"请提供 email 或配置支持的 identity_provider"
            )
        return identity

    def _build_otp_callback(
        self,
        identity,
        *,
        keyword: str = "",
        timeout: Optional[int] = None,
        code_pattern: Optional[str] = None,
        wait_message: str = "等待验证码...",
        success_label: str = "验证码",
    ):
        mailbox = getattr(self, "mailbox", None)
        mail_acct = getattr(identity, "mailbox_account", None)
        if not mailbox or not mail_acct:
            return None

        log = getattr(self, "_log_fn", print)

        def otp_cb():
            log(wait_message)
            kwargs = {"keyword": keyword, "before_ids": identity.before_ids}
            if timeout is not None:
                kwargs["timeout"] = timeout
            if code_pattern:
                kwargs["code_pattern"] = code_pattern
            code = mailbox.wait_for_code(mail_acct, **kwargs)
            if code:
                log(f"{success_label}: {code}")
            return code

        return otp_cb

    def _build_link_callback(
        self,
        identity,
        *,
        keyword: str = "",
        timeout: Optional[int] = None,
        wait_message: str = "等待验证链接邮件...",
        success_label: str = "验证链接",
        preview_chars: int = 80,
    ):
        mailbox = getattr(self, "mailbox", None)
        mail_acct = getattr(identity, "mailbox_account", None)
        if not mailbox or not mail_acct:
            return None

        log = getattr(self, "_log_fn", print)

        def link_cb():
            log(wait_message)
            before_ids = mailbox.get_current_ids(mail_acct)
            kwargs = {"keyword": keyword, "before_ids": before_ids}
            if timeout is not None:
                kwargs["timeout"] = timeout
            link = mailbox.wait_for_link(mail_acct, **kwargs)
            if link:
                preview = link if len(link) <= preview_chars else f"{link[:preview_chars]}..."
                log(f"{success_label}: {preview}")
            return link

        return link_cb
