import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  beginGlobalLoading,
  createWorkstation,
  deleteWorkstation,
  getWorkstations,
  regenerateWorkstationBindCode,
  testWorkstationConnectivity,
  updateWorkstation,
  type Workstation,
  type WorkstationInput,
} from '../api/client'
import { formatBeijingTime } from '../utils/time'

const CLIENT_DOWNLOAD_URL = '/api/downloads/client/latest'

const EMPTY_FORM: WorkstationInput = {
  name: '',
  kind: 'local',
  status: 'offline',
  host: '',
  ip_address: '',
  login_username: '',
  login_password: '',
  client_version: '1.0',
  notes: '',
}

const STATUS_LABEL: Record<string, string> = {
  offline: '离线',
  online: '在线',
  available: '可分配',
  busy: '使用中',
  maintenance: '维护中',
}

export function DownloadCenter({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [items, setItems] = useState<Workstation[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [managementOpen, setManagementOpen] = useState(false)
  const [editing, setEditing] = useState<Workstation | null>(null)
  const [form, setForm] = useState<WorkstationInput>(EMPTY_FORM)
  const [connectivityResult, setConnectivityResult] = useState<{ ok: boolean; message: string; target: string } | null>(null)

  const localCount = useMemo(() => items.filter(item => item.kind === 'local').length, [items])
  const cloudCount = useMemo(() => items.filter(item => item.kind === 'cloud').length, [items])
  const onlineCount = useMemo(() => items.filter(item => ['online', 'available', 'busy'].includes(item.status)).length, [items])

  const load = useCallback(async () => {
    try {
      setItems(await getWorkstations())
    } catch (err) {
      showToast(err instanceof Error ? err.message : '加载工作电脑失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => { load() }, [load])

  const openCreate = (kind: 'local' | 'cloud') => {
    setEditing(null)
    setForm({
      ...EMPTY_FORM,
      kind,
      status: kind === 'cloud' ? 'available' : 'offline',
      client_version: '1.0',
    })
    setConnectivityResult(null)
    setModalOpen(true)
  }

  const openEdit = (item: Workstation) => {
    setEditing(item)
    setForm({
      name: item.name,
      kind: item.kind,
      status: item.status,
      host: item.host,
      ip_address: item.ip_address,
      login_username: item.login_username,
      login_password: '',
      client_version: item.client_version || '1.0',
      notes: item.notes,
    })
    setConnectivityResult(null)
    setModalOpen(true)
  }

  const runConnectivityTest = async (): Promise<boolean> => {
    if (form.kind !== 'cloud') return true
    if (!form.host?.trim()) {
      showToast('云电脑需要填写公网地址', 'error')
      setConnectivityResult({ ok: false, message: '缺少连接地址', target: '' })
      return false
    }
    const stopLoading = beginGlobalLoading('正在测试云电脑连通性...')
    try {
      const result = await testWorkstationConnectivity({ host: form.host })
      const target = `${result.host}:${result.port}`
      setConnectivityResult({ ok: result.ok, message: result.ok ? '连通性正常' : result.message, target })
      if (!result.ok) {
        showToast(`云电脑无法连接：${target}`, 'error')
        return false
      }
      showToast(`云电脑连通性正常：${target}`, 'success')
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : '测试云电脑连通性失败'
      setConnectivityResult({ ok: false, message, target: '' })
      showToast(message, 'error')
      return false
    } finally {
      stopLoading()
    }
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) {
      showToast('请填写电脑名称', 'error')
      return
    }
    if (form.kind === 'cloud' && !form.host?.trim()) {
      showToast('云电脑需要填写公网地址', 'error')
      return
    }
    if (form.kind === 'cloud' && !(await runConnectivityTest())) {
      return
    }
    const stopLoading = beginGlobalLoading(editing ? '正在保存工作电脑...' : (form.kind === 'local' ? '正在生成本地电脑绑定码...' : '正在新增云电脑...'))
    try {
      const payload = { ...form, name: form.name.trim() }
      if (payload.kind === 'local') {
        delete payload.status
        delete payload.host
        delete payload.ip_address
        delete payload.login_username
        delete payload.login_password
        delete payload.client_version
      } else {
        payload.ip_address = ''
      }
      if (!payload.login_password) delete payload.login_password
      if (editing) {
        await updateWorkstation(editing.id, payload)
        showToast('工作电脑已更新', 'success')
      } else {
        await createWorkstation(payload)
        showToast(form.kind === 'local' ? '本地电脑绑定码已生成' : '云电脑已新增', 'success')
      }
      setModalOpen(false)
      await load()
    } catch (err) {
      showToast(err instanceof Error ? err.message : '保存工作电脑失败', 'error')
    } finally {
      stopLoading()
    }
  }

  const remove = async (item: Workstation) => {
    if (!confirm(`确定删除「${item.name}」吗？已绑定员工的电脑不能删除。`)) return
    const stopLoading = beginGlobalLoading('正在删除工作电脑...')
    try {
      await deleteWorkstation(item.id)
      showToast('工作电脑已删除', 'success')
      await load()
    } catch (err) {
      showToast(err instanceof Error ? err.message : '删除工作电脑失败', 'error')
    } finally {
      stopLoading()
    }
  }

  const copyBindCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code)
      showToast('绑定码已复制', 'success')
    } catch {
      showToast(`绑定码：${code}`, 'info')
    }
  }

  const refreshBindCode = async (item: Workstation) => {
    if (!confirm(`确定重新生成「${item.name}」的绑定码吗？旧绑定码会失效。`)) return
    const stopLoading = beginGlobalLoading('正在重新生成绑定码...')
    try {
      await regenerateWorkstationBindCode(item.id)
      showToast('绑定码已重新生成', 'success')
      await load()
    } catch (err) {
      showToast(err instanceof Error ? err.message : '重新生成绑定码失败', 'error')
    } finally {
      stopLoading()
    }
  }

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">工作环境</h1>
          <div className="office-subtitle">给客户本地电脑安装客户端，或从你提供的云电脑池分配运行环境。</div>
        </div>
      </div>

      <div className="client-hero">
        <div className="client-package">
          <div className="client-chip">工作电脑客户端</div>
          <p>客户安装后输入绑定码，电脑会主动连接平台。AI 员工被绑定到这台电脑后，浏览器、文件、飞书、企业微信等本机操作都在这台电脑执行。</p>
          <div className="client-action-row">
            <a className="btn btn-primary" href={CLIENT_DOWNLOAD_URL} download>下载客户端</a>
            <button className="btn btn-secondary" type="button" onClick={() => setManagementOpen(true)}>
              电脑管理
            </button>
          </div>
          <div className="task-meta" style={{ marginTop: 10 }}>客户端安装包由云服务统一提供；下载按钮会获取当前最新客户端。</div>
        </div>
        <div className="client-flow">
          {['后台生成绑定码', '客户下载并安装客户端', '输入绑定码主动连接平台', 'AI员工绑定该电脑执行'].map((step, index) => (
            <div key={step}>
              <span>{index + 1}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="workstation-stats">
        <div><span>本地客户端电脑</span><strong>{localCount}</strong></div>
        <div><span>云电脑池</span><strong>{cloudCount}</strong></div>
        <div><span>在线/可用电脑</span><strong>{onlineCount}</strong></div>
      </div>

      {managementOpen && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setManagementOpen(false) }}>
          <div className="modal-content computer-management-modal">
            <div className="modal-header">
              <div>
                <h3 className="modal-title">电脑管理</h3>
                <div className="task-meta">选择要添加的工作电脑类型。</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setManagementOpen(false)}>关闭</button>
            </div>
            <div className="computer-management-options">
              <button type="button" onClick={() => { setManagementOpen(false); openCreate('cloud') }}>
                <strong>新增云电脑</strong>
                <span>添加你提供的公网云电脑，保存前会校验连通性。</span>
              </button>
              <button type="button" onClick={() => { setManagementOpen(false); openCreate('local') }}>
                <strong>生成本地电脑绑定码</strong>
                <span>客户下载安装客户端后，用绑定码把局域网电脑接入平台。</span>
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="workstation-grid">
        {items.map(item => (
          <div key={item.id} className={`workstation-card ${item.kind}`}>
            <div className="workstation-card-head">
              <div>
                <span className="client-chip">{item.kind === 'cloud' ? '云电脑' : '本地客户端'}</span>
                <h3>{item.name}</h3>
              </div>
              <span className={`workstation-status ${item.status}`}>{STATUS_LABEL[item.status] || item.status}</span>
            </div>
            <div className="workstation-meta">
              <div><span>绑定码</span><strong>{item.bind_code}</strong></div>
              <div><span>{item.kind === 'cloud' ? '公网地址' : '连接方式'}</span><strong>{item.kind === 'cloud' ? (item.host || '未填写') : '客户端主动连接'}</strong></div>
              <div><span>{item.kind === 'cloud' ? '登录用户' : '本机信息'}</span><strong>{item.kind === 'cloud' ? (item.login_username || '未填写') : (item.last_seen_at ? '已上报' : '等待上报')}</strong></div>
              <div><span>已绑定员工</span><strong>{item.assigned_agent_count}</strong></div>
            </div>
            <p>{item.notes || (item.kind === 'cloud' ? '你提供给客户使用的云电脑资源。' : '等待客户安装客户端并完成绑定。')}</p>
            <div className="task-meta">
              {item.last_seen_at ? `最后心跳：${formatBeijingTime(item.last_seen_at)}` : `创建时间：${item.created_at ? formatBeijingTime(item.created_at) : '—'}`}
            </div>
            <div className="card-actions">
              {item.kind === 'local' && <button className="btn btn-secondary btn-sm" onClick={() => copyBindCode(item.bind_code)}>复制绑定码</button>}
              {item.kind === 'local' && <button className="btn btn-ghost btn-sm" onClick={() => refreshBindCode(item)}>重新生成</button>}
              <button className="btn btn-secondary btn-sm" onClick={() => openEdit(item)}>编辑</button>
              <button className="btn btn-ghost btn-sm danger-text" onClick={() => remove(item)}>删除</button>
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">PC</div>
            <div className="empty-text">还没有工作电脑。先生成本地电脑绑定码，或添加一台云电脑。</div>
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setModalOpen(false) }}>
          <div className="modal-content workstation-modal">
            <div className="modal-header">
              <div>
                <h3 className="modal-title">{editing ? '编辑工作电脑' : (form.kind === 'local' ? '生成本地电脑绑定码' : '新增云电脑')}</h3>
                <div className="task-meta">本地电脑由客户端主动连接并上报机器信息；云电脑可以作为你提供给客户的资源池。</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setModalOpen(false)}>关闭</button>
            </div>
            <form onSubmit={submit} className="task-form">
              <div className="form-grid">
                <label>
                  <span>{form.kind === 'local' ? '绑定名称' : '电脑名称'}</span>
                  <input className="form-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder={form.kind === 'local' ? '例如：运营部本地电脑绑定' : '例如：云电脑-运营-01'} required />
                </label>
                <label>
                  <span>电脑类型</span>
                  <select className="form-select" value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value as 'local' | 'cloud' })}>
                    <option value="local">本地客户端电脑</option>
                    <option value="cloud">云电脑池</option>
                  </select>
                </label>
                {form.kind === 'cloud' && (
                  <>
                    <label>
                      <span>状态</span>
                      <select className="form-select" value={form.status} onChange={e => setForm({ ...form, status: e.target.value as WorkstationInput['status'] })}>
                        <option value="offline">离线</option>
                        <option value="online">在线</option>
                        <option value="available">可分配</option>
                        <option value="busy">使用中</option>
                        <option value="maintenance">维护中</option>
                      </select>
                    </label>
                    <label>
                      <span>公网地址 / 远程地址</span>
                      <input className="form-input" value={form.host} onChange={e => setForm({ ...form, host: e.target.value })} placeholder="例如：1.2.3.4 或 cloud.example.com:3389" />
                    </label>
                    <label>
                      <span>登录用户名</span>
                      <input className="form-input" value={form.login_username} onChange={e => setForm({ ...form, login_username: e.target.value })} placeholder="可选" />
                    </label>
                    <label>
                      <span>登录密码</span>
                      <input className="form-input" type="password" value={form.login_password} onChange={e => setForm({ ...form, login_password: e.target.value })} placeholder={editing?.password_set ? '已保存，留空不修改' : '可选'} />
                    </label>
                    <div className="cloud-connectivity-row">
                      <button type="button" className="btn btn-secondary" onClick={runConnectivityTest}>测试连通性</button>
                      <span>默认测试 3389 端口；地址可填写 example.com:端口。</span>
                    </div>
                  </>
                )}
              </div>
              {form.kind === 'cloud' && connectivityResult && (
                <div className={connectivityResult.ok ? 'form-help-info' : 'form-help-error'}>
                  {connectivityResult.ok
                    ? `云电脑连通性正常：${connectivityResult.target}`
                    : `云电脑连通性失败：${connectivityResult.target ? `${connectivityResult.target}，` : ''}${connectivityResult.message}`}
                </div>
              )}
              <label>
                <span>说明</span>
                <textarea className="form-textarea" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="例如：这台电脑已经登录企业微信和飞书，适合运营部员工使用。" />
              </label>
              {form.kind === 'local' && (
                <div className="form-help-info">保存后系统会生成绑定码。客户在本地电脑打开客户端输入绑定码，客户端会主动连接平台并自动上报机器名、内网 IP、系统信息和在线状态。</div>
              )}
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setModalOpen(false)}>取消</button>
                <button type="submit" className="btn btn-primary">保存</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
