import { useState } from 'react'
import { beginGlobalLoading, login, registerEnterprise, setToken, type AuthResult } from '../api/client'

type Mode = 'enterprise_login' | 'enterprise_register' | 'employee_login'

export function Entry({
  onAuthenticated,
  showToast,
}: {
  onAuthenticated: (result: AuthResult) => void
  showToast: (msg: string, type: string) => void
}) {
  const [mode, setMode] = useState<Mode>('enterprise_login')
  const [loading, setLoading] = useState(false)
  const [pointer, setPointer] = useState({ x: 50, y: 42 })

  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [registerForm, setRegisterForm] = useState({
    enterprise_name: '',
    admin_username: '',
    admin_password: '',
    plan: 'formal' as 'trial' | 'formal',
    billing_period: 'monthly' as 'monthly' | 'yearly',
    payment_method: 'wechat' as 'wechat' | 'alipay',
  })

  const submitLogin = async (employee = false) => {
    if (!loginForm.username.trim() || !loginForm.password.trim()) {
      showToast('请输入账号和密码', 'error')
      return
    }
    setLoading(true)
    const stopLoading = beginGlobalLoading(employee ? '正在登录员工账号...' : '正在登录企业账号...')
    try {
      const result = await login({
        username: loginForm.username.trim(),
        password: loginForm.password,
      })
      if (employee && result.user.role !== 'employee') {
        showToast('该账号不是员工账号，请走企业入口登录', 'error')
        return
      }
      if (!employee && result.user.role !== 'admin') {
        showToast('该账号不是企业管理员，请走员工入口登录', 'error')
        return
      }
      setToken(result.token)
      onAuthenticated(result)
      showToast('登录成功', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '登录失败', 'error')
    } finally {
      stopLoading()
      setLoading(false)
    }
  }

  const submitRegister = async () => {
    if (!registerForm.enterprise_name.trim() || !registerForm.admin_username.trim() || !registerForm.admin_password.trim()) {
      showToast('请完整填写企业注册信息', 'error')
      return
    }
    setLoading(true)
    const stopLoading = beginGlobalLoading('正在注册企业并创建管理员...')
    try {
      const result = await registerEnterprise(registerForm)
      setToken(result.token)
      onAuthenticated(result)
      if (result.payment_required) {
        showToast('企业创建成功，当前为待支付状态（支付接口待接入）', 'success')
      } else {
        showToast('企业创建成功', 'success')
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : '企业注册失败', 'error')
    } finally {
      stopLoading()
      setLoading(false)
    }
  }

  return (
    <div
      className="entry-page"
      style={{ '--entry-x': `${pointer.x}%`, '--entry-y': `${pointer.y}%` } as React.CSSProperties}
      onMouseMove={e => {
        const rect = e.currentTarget.getBoundingClientRect()
        setPointer({
          x: ((e.clientX - rect.left) / rect.width) * 100,
          y: ((e.clientY - rect.top) / rect.height) * 100,
        })
      }}
    >
      <div className="entry-orbit entry-orbit-a" />
      <div className="entry-orbit entry-orbit-b" />
      <div className="entry-grid-glow" />
      <div className="entry-card">
        <div className="entry-brand">
          <img src="/logo.svg" alt="AI 员工平台" />
          <div>
            <div className="entry-kicker">Enterprise AI Workforce</div>
            <h1>AI 员工平台</h1>
            <p>企业 AI 员工、任务调度和自动化协作系统</p>
          </div>
        </div>
        <div className="workspace-tabs">
          <button className={mode === 'enterprise_login' ? 'active' : ''} onClick={() => setMode('enterprise_login')}>企业登录</button>
          <button className={mode === 'enterprise_register' ? 'active' : ''} onClick={() => setMode('enterprise_register')}>企业注册</button>
          <button className={mode === 'employee_login' ? 'active' : ''} onClick={() => setMode('employee_login')}>员工登录</button>
        </div>

        {(mode === 'enterprise_login' || mode === 'employee_login') && (
          <div className="task-form" style={{ marginTop: 16 }}>
            <label>
              <span>{mode === 'employee_login' ? '员工账号' : '管理员账号'}</span>
              <input
                className="form-input"
                value={loginForm.username}
                onChange={e => setLoginForm({ ...loginForm, username: e.target.value })}
                placeholder="请输入登录账号"
              />
            </label>
            <label>
              <span>密码</span>
              <input
                className="form-input"
                type="password"
                value={loginForm.password}
                onChange={e => setLoginForm({ ...loginForm, password: e.target.value })}
                placeholder="请输入密码"
              />
            </label>
            <button className="btn btn-primary" onClick={() => submitLogin(mode === 'employee_login')} disabled={loading}>
              {loading ? '提交中...' : '登录'}
            </button>
          </div>
        )}

        {mode === 'enterprise_register' && (
          <div className="task-form" style={{ marginTop: 16 }}>
            <label>
              <span>企业名称</span>
              <input className="form-input" value={registerForm.enterprise_name} onChange={e => setRegisterForm({ ...registerForm, enterprise_name: e.target.value })} />
            </label>
            <label>
              <span>管理员账号</span>
              <input className="form-input" value={registerForm.admin_username} onChange={e => setRegisterForm({ ...registerForm, admin_username: e.target.value })} />
            </label>
            <label>
              <span>管理员密码</span>
              <input className="form-input" type="password" value={registerForm.admin_password} onChange={e => setRegisterForm({ ...registerForm, admin_password: e.target.value })} />
            </label>
            <div className="form-grid">
              <label>
                <span>版本</span>
                <select className="form-select" value={registerForm.plan} onChange={e => setRegisterForm({ ...registerForm, plan: e.target.value as 'trial' | 'formal' })}>
                  <option value="trial">体验版</option>
                  <option value="formal">正式版</option>
                </select>
              </label>
              <label>
                <span>付费周期</span>
                <select className="form-select" value={registerForm.billing_period} onChange={e => setRegisterForm({ ...registerForm, billing_period: e.target.value as 'monthly' | 'yearly' })}>
                  <option value="monthly">月付（98元）</option>
                  <option value="yearly">年付（85折）</option>
                </select>
              </label>
            </div>
            <label>
              <span>支付方式</span>
              <select className="form-select" value={registerForm.payment_method} onChange={e => setRegisterForm({ ...registerForm, payment_method: e.target.value as 'wechat' | 'alipay' })}>
                <option value="wechat">微信支付</option>
                <option value="alipay">支付宝</option>
              </select>
            </label>
            <button className="btn btn-primary" onClick={submitRegister} disabled={loading}>
              {loading ? '提交中...' : '注册企业并创建管理员'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
