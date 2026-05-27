import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getLLMConfig,
  refreshLLMModels,
  saveProviderApiKey,
  setDefaultModel,
  type LLMConfig,
  type ProviderInfo,
} from '../api/client'

export function ModelManagement({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [config, setConfig] = useState<LLMConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeProvider, setActiveProvider] = useState<string | null>(null)
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [query, setQuery] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await getLLMConfig()
      setConfig(data)
      setActiveProvider(prev => prev || data.default_provider || data.providers[0]?.name || null)
    } catch {
      showToast('加载模型配置失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => { load() }, [load])

  const providers = config?.providers || []
  const active = providers.find(p => p.name === activeProvider) || providers[0]
  const readyProviders = providers.filter(p => p.configured && p.status === 'ready')

  const filteredProviders = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return providers
    return providers.filter(provider => [
      provider.display_name,
      provider.name,
      provider.models.map(m => `${m.name} ${m.display_name}`).join(' '),
    ].join(' ').toLowerCase().includes(q))
  }, [providers, query])

  const saveKey = async (provider: ProviderInfo) => {
    const apiKey = keys[provider.name]?.trim()
    if (!apiKey) {
      showToast('请先输入 API Key', 'error')
      return
    }
    try {
      await saveProviderApiKey(provider.name, apiKey)
      setKeys(prev => ({ ...prev, [provider.name]: '' }))
      await load()
      showToast(`${provider.display_name} 已启用`, 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : '保存 API Key 失败', 'error')
    }
  }

  const chooseDefault = async (provider: ProviderInfo, model: string) => {
    if (provider.status !== 'ready') {
      showToast('该厂商还未接入运行时适配器', 'error')
      return
    }
    if (!provider.configured) {
      showToast('请先配置该厂商 API Key', 'error')
      return
    }
    try {
      await setDefaultModel(provider.name, model)
      await load()
      showToast('默认模型已更新', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : '设置默认模型失败', 'error')
    }
  }

  const refreshModels = async () => {
    setRefreshing(true)
    try {
      const result = await refreshLLMModels()
      setConfig(result)
      const updatedCount = result.updated.filter(item => item.status === 'updated').length
      const skippedCount = result.updated.filter(item => item.status === 'skipped').length
      showToast(`模型列表已更新：${updatedCount} 个厂商已同步，${skippedCount} 个厂商缺少 Key`, 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : '更新模型列表失败', 'error')
    } finally {
      setRefreshing(false)
    }
  }

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>
  if (!config || !active) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>暂无模型配置</div>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">模型管理</h1>
          <div className="office-subtitle">统一维护 LLM 厂商、API Key 和默认模型。</div>
        </div>
        <button className="btn btn-primary" onClick={refreshModels} disabled={refreshing}>
          {refreshing ? '更新中...' : '更新所有模型'}
        </button>
      </div>

      <div className="model-overview">
        <div>
          <span>当前默认模型</span>
          <strong>{config.default_provider} / {config.default_model}</strong>
        </div>
        <div>
          <span>已可用厂商</span>
          <strong>{readyProviders.length}</strong>
        </div>
        <div>
          <span>可选模型</span>
          <strong>{providers.reduce((sum, p) => sum + p.models.length, 0)}</strong>
        </div>
        <div>
          <span>上次更新</span>
          <strong>{config.last_model_refresh_at ? new Date(config.last_model_refresh_at).toLocaleString('zh-CN', { hour12: false }) : '未同步'}</strong>
        </div>
      </div>

      <div className="model-layout">
        <aside className="model-sidebar">
          <input className="form-input" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索厂商或模型" />
          <div className="provider-list">
            {filteredProviders.map(provider => (
              <button
                key={provider.name}
                className={`provider-item ${active.name === provider.name ? 'active' : ''}`}
                onClick={() => setActiveProvider(provider.name)}
              >
                <span className={`provider-status ${provider.configured ? 'on' : ''}`} />
                <div>
                  <strong>{provider.display_name}</strong>
                  <small>{provider.models.length} 个模型 · {provider.configured ? '已配置' : '未配置'}</small>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="model-main">
          <div className="model-provider-card">
            <div>
              <h2>{active.display_name}</h2>
              <p>{active.protocol === 'openai_compatible' ? 'OpenAI 兼容接口，可直接用于 AI 员工。' : '原生协议厂商，待运行时适配器接入。'}</p>
              <code>{active.base_url || active.protocol}</code>
            </div>
              <span className={`model-badge ${active.configured ? 'ready' : ''}`}>
              {active.status === 'ready' ? (active.configured ? '已可用' : '待填 Key') : '待适配'}
            </span>
          </div>
          {active.last_refreshed_at && (
            <div className="task-meta" style={{ marginBottom: 12 }}>
              {active.display_name} 上次模型同步：{new Date(active.last_refreshed_at).toLocaleString('zh-CN', { hour12: false })}
            </div>
          )}

          <div className="key-panel">
            <div>
              <div className="panel-title">API Key</div>
              <div className="task-meta">保存到后端本地环境变量：{active.api_key_env}</div>
            </div>
            <div className="key-input-row">
              <input
                className="form-input"
                type="password"
                value={keys[active.name] || ''}
                onChange={e => setKeys(prev => ({ ...prev, [active.name]: e.target.value }))}
                placeholder={active.configured ? '已配置，输入新 Key 可覆盖' : '粘贴 API Key'}
                disabled={active.status !== 'ready'}
              />
              <button className="btn btn-primary" onClick={() => saveKey(active)} disabled={active.status !== 'ready'}>保存并启用</button>
            </div>
          </div>

          <div className="model-grid">
            {active.models.map(model => {
              const isDefault = config.default_provider === active.name && config.default_model === model.name
              return (
                <div key={model.name} className={`model-card ${isDefault ? 'selected' : ''}`}>
                  <div>
                    <div className="model-name">{model.display_name}</div>
                    <code>{model.name}</code>
                    <p>{model.description}</p>
                  </div>
                  <button
                    className={isDefault ? 'btn btn-secondary btn-sm' : 'btn btn-primary btn-sm'}
                    onClick={() => chooseDefault(active, model.name)}
                    disabled={isDefault || active.status !== 'ready'}
                  >
                    {isDefault ? '当前默认' : '设为默认'}
                  </button>
                </div>
              )
            })}
          </div>
        </section>
      </div>
    </div>
  )
}
