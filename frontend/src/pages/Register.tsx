import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Play, CheckCircle, XCircle, Loader2 } from 'lucide-react'

const FALLBACK_PLATFORMS = [
  { name: 'chatgpt', display_name: 'ChatGPT' },
  { name: 'cursor', display_name: 'Cursor' },
  { name: 'grok', display_name: 'Grok' },
  { name: 'kiro', display_name: 'Kiro (AWS Builder ID)' },
  { name: 'openblocklabs', display_name: 'OpenBlockLabs' },
  { name: 'tavily', display_name: 'Tavily' },
  { name: 'trae', display_name: 'Trae.ai' },
]

export default function Register() {
  const [form, setForm] = useState({
    platform: 'trae',
    email: '',
    password: '',
    count: 1,
    proxy: '',
    executor_type: 'protocol',
    captcha_solver: 'yescaptcha',
    identity_provider: 'mailbox',
    oauth_provider: '',
    oauth_email_hint: '',
    chrome_user_data_dir: '',
    chrome_cdp_url: '',
    mail_provider: 'moemail',
    laoudo_auth: '',
    laoudo_email: '',
    laoudo_account_id: '',
    cfworker_api_url: '',
    cfworker_admin_token: '',
    cfworker_domain: '',
    cfworker_fingerprint: '',
    yescaptcha_key: '',
    solver_url: 'http://localhost:8889',
  })
  const [platforms, setPlatforms] = useState<any[]>([])
  const [task, setTask] = useState<any>(null)
  const [polling, setPolling] = useState(false)

  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }))

  useEffect(() => {
    Promise.all([
      apiFetch('/config').catch(() => ({})),
      apiFetch('/platforms').catch(() => []),
    ]).then(([cfg, ps]) => {
      setPlatforms(ps || [])
      setForm(f => ({
        ...f,
        executor_type: cfg.default_executor || f.executor_type,
        captcha_solver: cfg.default_captcha_solver || f.captcha_solver,
        identity_provider: cfg.default_identity_provider || f.identity_provider,
        oauth_provider: cfg.default_oauth_provider || f.oauth_provider,
        oauth_email_hint: cfg.oauth_email_hint || f.oauth_email_hint,
        chrome_user_data_dir: cfg.chrome_user_data_dir || f.chrome_user_data_dir,
        chrome_cdp_url: cfg.chrome_cdp_url || f.chrome_cdp_url,
        mail_provider: cfg.mail_provider || f.mail_provider,
        laoudo_auth: cfg.laoudo_auth || f.laoudo_auth,
        laoudo_email: cfg.laoudo_email || f.laoudo_email,
        laoudo_account_id: cfg.laoudo_account_id || f.laoudo_account_id,
        cfworker_api_url: cfg.cfworker_api_url || f.cfworker_api_url,
        cfworker_admin_token: cfg.cfworker_admin_token || f.cfworker_admin_token,
        cfworker_domain: cfg.cfworker_domain || f.cfworker_domain,
        cfworker_fingerprint: cfg.cfworker_fingerprint || f.cfworker_fingerprint,
        yescaptcha_key: cfg.yescaptcha_key || f.yescaptcha_key,
      }))
    })
  }, [])

  const currentPlatform = platforms.find((p: any) => p.name === form.platform) || null
  const platformOptionsSource = platforms.length > 0 ? platforms : FALLBACK_PLATFORMS
  const platformOptions = platformOptionsSource.map((p: any) => [p.name, p.display_name])
  const supportedExecutors = currentPlatform?.supported_executors || ['protocol']
  const supportedIdentityModes = currentPlatform?.supported_identity_modes || ['mailbox']
  const supportedOAuthProviders = currentPlatform?.supported_oauth_providers || []
  const supportedExecutorsKey = supportedExecutors.join('|')
  const supportedIdentityModesKey = supportedIdentityModes.join('|')
  const supportedOAuthProvidersKey = supportedOAuthProviders.join('|')
  const identityProviderOptions = [
    ['mailbox', '系统自动完成'],
    ['oauth_browser', '浏览器自动/人工完成'],
  ].filter(([value]) => supportedIdentityModes.includes(value))
  const oauthProviderOptions = [
    ['', '不预选，我自己在页面里选'],
    ['github', 'GitHub'],
    ['google', 'Google'],
    ['microsoft', 'Microsoft'],
    ['linkedin', 'LinkedIn'],
    ['apple', 'Apple'],
    ['x', 'X'],
    ['builderid', 'Builder ID'],
  ].filter(([value]) => supportedOAuthProviders.includes(value))

  useEffect(() => {
    if (!platformOptionsSource.some((p: any) => p.name === form.platform)) {
      const fallback = platformOptionsSource[0]?.name || 'trae'
      if (fallback !== form.platform) {
        set('platform', fallback)
      }
    }
  }, [form.platform, platforms.length])

  useEffect(() => {
    if (!identityProviderOptions.some(([value]) => value === form.identity_provider)) {
      const fallback = identityProviderOptions[0]?.[0] || 'mailbox'
      if (fallback !== form.identity_provider) {
        set('identity_provider', fallback)
      }
    }
  }, [form.identity_provider, form.platform, supportedIdentityModesKey])

  useEffect(() => {
    if (form.identity_provider === 'oauth_browser' && supportedExecutors.includes('headed') && form.executor_type !== 'headed') {
      set('executor_type', 'headed')
    }
  }, [form.executor_type, form.identity_provider, supportedExecutorsKey])

  useEffect(() => {
    if (form.identity_provider !== 'oauth_manual') {
      return
    }
    if (!oauthProviderOptions.some(([value]) => value === form.oauth_provider)) {
      const fallback = oauthProviderOptions[0]?.[0] || ''
      if (fallback !== form.oauth_provider) {
        set('oauth_provider', fallback)
      }
    }
  }, [form.identity_provider, form.oauth_provider, supportedOAuthProvidersKey])

  const submit = async () => {
    const res = await apiFetch('/tasks/register', {
      method: 'POST',
      body: JSON.stringify({
        platform: form.platform,
        email: form.email || null,
        password: form.password || null,
        count: form.count,
        proxy: form.proxy || null,
        executor_type: form.executor_type,
        captcha_solver: form.captcha_solver,
        extra: {
          mail_provider: form.mail_provider,
          laoudo_auth: form.laoudo_auth,
          laoudo_email: form.laoudo_email,
          laoudo_account_id: form.laoudo_account_id,
          cfworker_api_url: form.cfworker_api_url,
          cfworker_admin_token: form.cfworker_admin_token,
          cfworker_domain: form.cfworker_domain,
          cfworker_fingerprint: form.cfworker_fingerprint,
          yescaptcha_key: form.yescaptcha_key,
          solver_url: form.solver_url,
          identity_provider: form.identity_provider,
          oauth_provider: form.oauth_provider,
          oauth_email_hint: form.oauth_email_hint,
          chrome_user_data_dir: form.chrome_user_data_dir || undefined,
          chrome_cdp_url: form.chrome_cdp_url || undefined,
        },
      }),
    })
    setTask(res)
    setPolling(true)
    pollTask(res.task_id)
  }

  const pollTask = async (id: string) => {
    const interval = setInterval(async () => {
      const t = await apiFetch(`/tasks/${id}`)
      setTask(t)
      if (t.status === 'done' || t.status === 'failed') {
        clearInterval(interval)
        setPolling(false)
        // 自动打开 cashier_url（Trae Pro 升级链接）
        if (t.cashier_urls && t.cashier_urls.length > 0) {
          t.cashier_urls.forEach((url: string) => window.open(url, '_blank'))
        }
      }
    }, 2000)
  }

  const Input = ({ label, k, type = 'text', placeholder = '' }: any) => (
    <div>
      <label className="block text-xs text-[var(--text-muted)] mb-1">{label}</label>
      <input
        type={type}
        value={(form as any)[k]}
        onChange={e => set(k, type === 'number' ? Number(e.target.value) : e.target.value)}
        placeholder={placeholder}
        className="w-full bg-[var(--bg-hover)] border border-[var(--border)] text-[var(--text-primary)] rounded-md px-3 py-2 text-sm focus:outline-none focus:border-indigo-500"
      />
    </div>
  )

  const Select = ({ label, k, options }: any) => (
    <div>
      <label className="block text-xs text-[var(--text-muted)] mb-1">{label}</label>
      <select
        value={(form as any)[k]}
        onChange={e => set(k, e.target.value)}
        className="w-full bg-[var(--bg-hover)] border border-[var(--border)] text-[var(--text-primary)] rounded-md px-3 py-2 text-sm focus:outline-none focus:border-indigo-500"
      >
        {options.map(([v, l]: any) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  )

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">注册任务</h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">创建账号自动注册任务</p>
      </div>

      <Card>
        <CardHeader><CardTitle>基本配置</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Select label="平台" k="platform" options={platformOptions} />
          <Select label="执行器" k="executor_type" options={supportedExecutors.map((value: string) => [
            value,
            value === 'protocol' ? '纯协议' : value === 'headless' ? '无头浏览器' : '有头浏览器',
          ])} />
          <Select label="验证码" k="captcha_solver" options={[['yescaptcha','YesCaptcha'],['local_solver','本地Solver(Camoufox)'],['manual','手动']]} />
          <Select label="注册方式" k="identity_provider" options={identityProviderOptions} />
          {form.identity_provider === 'oauth_browser' && oauthProviderOptions.length > 0 && (
            <>
              <Select label="浏览器默认登录入口" k="oauth_provider" options={oauthProviderOptions} />
              <Input label="预期登录邮箱" k="oauth_email_hint" placeholder="your-account@example.com" />
              <Input label="Chrome Profile 路径 (可选，全自动 OAuth)" k="chrome_user_data_dir" placeholder="~/Library/Application Support/Google/Chrome" />
              <Input label="Chrome CDP 地址 (可选)" k="chrome_cdp_url" placeholder="http://localhost:9222" />
              <p className="text-xs text-[var(--text-muted)]">
                填写 Chrome Profile 路径后，使用本机已登录的 Google/GitHub session 全自动完成 OAuth，无需人工干预。留空则打开普通浏览器，需要手动登录。
              </p>
            </>
          )}
          <div className="grid grid-cols-2 gap-4">
            <Input label="批量数量" k="count" type="number" />
            <Input label="代理 (可选)" k="proxy" placeholder="http://user:pass@host:port" />
          </div>
          {form.platform === 'tavily' && form.identity_provider === 'oauth_browser' && (
            <p className="text-xs text-[var(--text-muted)]">Tavily 当前普通邮箱密码自动注册已受限。若选"浏览器人工完成"，需要在可见浏览器中自己完成登录或授权。</p>
          )}
        </CardContent>
      </Card>

      {form.identity_provider === 'mailbox' && (
      <Card>
        <CardHeader><CardTitle>邮箱配置</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Select label="邮箱服务" k="mail_provider" options={[['moemail','MoeMail (sall.cc)'],['laoudo','Laoudo'],['cfworker','CF Worker']]} />
          {form.mail_provider === 'laoudo' && (<>
            <Input label="邮箱地址" k="laoudo_email" placeholder="xxx@laoudo.com" />
            <Input label="Account ID" k="laoudo_account_id" placeholder="563" />
            <Input label="JWT Token" k="laoudo_auth" placeholder="eyJ..." />
          </>)}
          {form.mail_provider === 'cfworker' && (<>
            <Input label="API URL" k="cfworker_api_url" placeholder="https://apimail.example.com" />
            <Input label="Admin Token" k="cfworker_admin_token" placeholder="abc123,,,abc" />
            <Input label="域名" k="cfworker_domain" placeholder="example.com" />
            <Input label="Fingerprint (可选)" k="cfworker_fingerprint" placeholder="cfb82279f..." />
          </>)}
        </CardContent>
      </Card>
      )}

      {form.captcha_solver === 'yescaptcha' && (
        <Card>
          <CardHeader><CardTitle>验证码配置</CardTitle></CardHeader>
          <CardContent>
            <Input label="YesCaptcha Key" k="yescaptcha_key" />
          </CardContent>
        </Card>
      )}
      {form.captcha_solver === 'local_solver' && (
        <Card>
          <CardHeader><CardTitle>本地 Solver 配置</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input label="Solver URL" k="solver_url" />
            <p className="text-xs text-[var(--text-muted)]">启动命令: python services/turnstile_solver/start.py --browser_type camoufox</p>
          </CardContent>
        </Card>
      )}

      <Button onClick={submit} disabled={polling} className="w-full">
        {polling ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />注册中...</> : <><Play className="h-4 w-4 mr-2" />开始注册</>}
      </Button>

      {task && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              任务状态
              <Badge variant={
                task.status === 'done' ? 'success' :
                task.status === 'failed' ? 'danger' : 'default'
              }>{task.status}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between text-[var(--text-muted)]">
              <span>任务 ID</span><span className="font-mono">{task.id}</span>
            </div>
            <div className="flex justify-between text-[var(--text-muted)]">
              <span>进度</span><span>{task.progress}</span>
            </div>
            {task.success != null && (
              <div className="flex items-center gap-2 text-emerald-400">
                <CheckCircle className="h-4 w-4" />
                成功 {task.success} 个
              </div>
            )}
            {task.errors?.length > 0 && (
              <div className="space-y-1">
                {task.errors.map((e: string, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-red-400">
                    <XCircle className="h-4 w-4" />
                    <span className="text-xs">{e}</span>
                  </div>
                ))}
              </div>
            )}
            {task.error && (
              <div className="flex items-center gap-2 text-red-400">
                <XCircle className="h-4 w-4" />
                <span className="text-xs">{task.error}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
