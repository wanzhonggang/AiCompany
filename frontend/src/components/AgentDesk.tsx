import { useMemo } from 'react'
import type { Agent } from '../api/client'

function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

const SKIN_TONES = ['#f5c6a0', '#e8b88a', '#d4a574', '#c68e5b', '#f0d5b0', '#e0c7a0']
const HAIR_COLORS = ['#1a1a2e', '#4a3728', '#8b6914', '#c4a35a', '#2d2d2d', '#6b3a2e', '#d4a017']
const SHIRT_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#3b82f6', '#8b5cf6', '#06b6d4']
const HAIR_STYLES = ['short', 'medium', 'spiky', 'curly', 'side', 'bald']

function getAppearance(agentId: string) {
  const h = hashString(agentId)
  return {
    skinTone: SKIN_TONES[h % SKIN_TONES.length],
    hairColor: HAIR_COLORS[Math.floor((h * 0.37) % 1 * HAIR_COLORS.length)],
    shirtColor: SHIRT_COLORS[Math.floor((h * 0.61) % 1 * SHIRT_COLORS.length)],
    hairStyle: HAIR_STYLES[Math.floor((h * 0.23) % 1 * HAIR_STYLES.length)],
    hasGlasses: h % 3 === 0,
    screenVariant: h % 5,
    deskVariant: h % 4,
    wallHue: 170 + (h % 80),
  }
}

// --- Screen content by agent status ---

function ScreenDashboard({ seed }: { seed: number }) {
  const bars = Array.from({ length: 6 }, (_, i) => 18 + ((seed + i * 19) % 58))

  return (
    <div className="screen-dashboard">
      <div className="screen-topbar">
        <span />
        <span />
        <span />
      </div>
      <div className="dash-card wide">
        {bars.slice(0, 4).map((height, i) => (
          <i key={i} style={{ height: `${height}%` }} />
        ))}
      </div>
      <div className="dash-grid">
        <div className="dash-ring" />
        <div className="dash-lines">
          {bars.slice(2).map((width, i) => <span key={i} style={{ width: `${width}%` }} />)}
        </div>
      </div>
    </div>
  )
}

function ScreenDoc({ agent }: { agent: Agent }) {
  const title = agent.role.slice(0, 5) || agent.name.slice(0, 5)

  return (
    <div className="screen-doc">
      <div className="doc-title">{title}</div>
      <div className="doc-line strong" />
      <div className="doc-line" />
      <div className="doc-line short" />
      <div className="doc-table">
        {Array.from({ length: 9 }, (_, i) => <span key={i} />)}
      </div>
    </div>
  )
}

function ScreenTerminal({ seed }: { seed: number }) {
  const prompts = ['run task', 'read file', 'write report', 'check api', 'sync data']

  return (
    <div className="screen-terminal">
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i}>
          <b>$</b> {prompts[(seed + i) % prompts.length]}
        </span>
      ))}
      <i />
    </div>
  )
}

function ScreenBoard({ agent }: { agent: Agent }) {
  const items = ['todo', 'doing', 'done']

  return (
    <div className="screen-board">
      <div className="board-title">{agent.current_task ? 'TASK' : 'PLAN'}</div>
      <div className="board-cols">
        {items.map((item, i) => (
          <div key={item} className="board-col">
            <b>{item}</b>
            <span style={{ width: `${72 - i * 12}%` }} />
            <span style={{ width: `${46 + i * 11}%` }} />
          </div>
        ))}
      </div>
    </div>
  )
}

function ScreenCalendar({ seed }: { seed: number }) {
  return (
    <div className="screen-calendar">
      <div className="calendar-head" />
      <div className="calendar-grid">
        {Array.from({ length: 21 }, (_, i) => (
          <span key={i} className={(i + seed) % 6 === 0 ? 'busy' : ''} />
        ))}
      </div>
    </div>
  )
}

function ScreenContent({ agent, variant }: { agent: Agent; variant: number }) {
  const status = agent.status
  const seed = hashString(agent.id + agent.role)

  if (status === 'working') {
    const codeLineWidths = Array.from({ length: 8 }, (_, i) => 28 + ((i * 37) % 58))
    if (variant === 1) return <ScreenDashboard seed={seed} />
    if (variant === 2) return <ScreenDoc agent={agent} />
    if (variant === 3) return <ScreenTerminal seed={seed} />
    if (variant === 4) return <ScreenBoard agent={agent} />

    return (
      <div className="screen-code">
        <div className="code-lines">
          {Array.from({ length: 8 }, (_, i) => (
            <span key={i} className="code-line" style={{ width: `${codeLineWidths[i]}%`, animationDelay: `${i * 0.12}s` }}>
              <span className="code-keyword">{['def', 'import', 'class', 'async', 'return', 'const', 'export', 'await'][i]}</span>
              {' '}{['getData()', 'numpy as np', 'Worker:', 'fetch()', 'result', 'x => x*2', 'default', 'sleep(1)'][i]}
            </span>
          ))}
        </div>
        <div className="screen-cursor" />
      </div>
    )
  }

  if (status === 'blocked') {
    return (
      <div className="screen-error">
        <div className="error-icon">!</div>
        <div className="error-text">{variant % 2 ? 'BLOCKED' : 'ERROR'}</div>
        <div className="error-stack">{variant % 2 ? 'Waiting for input' : 'Connection refused'}</div>
      </div>
    )
  }

  if (status === 'completed') {
    return (
      <div className="screen-success">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M5 13l4 4L19 7" />
        </svg>
        <div className="success-text">DONE</div>
      </div>
    )
  }

  if (variant === 1) return <ScreenCalendar seed={seed} />
  if (variant === 2) return <ScreenDashboard seed={seed} />
  if (variant === 3) return <ScreenDoc agent={agent} />
  if (variant === 4) return <ScreenTerminal seed={seed} />

  return (
    <div className="screen-game">
      <div className="game-paddle" />
      <div className="game-ball" />
      <div className="game-brick" style={{ top: '15%', left: '20%' }} />
      <div className="game-brick" style={{ top: '15%', left: '45%' }} />
      <div className="game-brick" style={{ top: '15%', left: '70%' }} />
      <div className="game-brick" style={{ top: '30%', left: '10%' }} />
      <div className="game-brick" style={{ top: '30%', left: '35%' }} />
      <div className="game-brick" style={{ top: '30%', left: '60%' }} />
      <div className="game-brick" style={{ top: '30%', left: '80%' }} />
    </div>
  )
}

// --- Hair styles ---

function Hair({ style, color }: { style: string; color: string }) {
  if (style === 'bald') return null

  if (style === 'short') {
    return (
      <div className="hair-short" style={{ background: color }}>
        <div className="hair-fringe" style={{ background: color }} />
      </div>
    )
  }

  if (style === 'spiky') {
    return (
      <div className="hair-spiky">
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className="hair-spike" style={{
            background: color,
            left: `${12 + i * 10}px`,
            height: `${8 + Math.sin(i * 0.9) * 6}px`,
            transform: `rotate(${(i - 3) * 12}deg)`,
          }} />
        ))}
      </div>
    )
  }

  if (style === 'curly') {
    return (
      <div className="hair-curly">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="hair-curl" style={{
            background: color,
            left: `${10 + i * 14}px`,
            width: '16px',
            height: '16px',
          }} />
        ))}
      </div>
    )
  }

  if (style === 'side') {
    return (
      <div className="hair-side">
        <div className="hair-part-left" style={{ background: color }} />
        <div className="hair-part-right" style={{ background: color }} />
        <div className="hair-top" style={{ background: color }} />
      </div>
    )
  }

  // medium (default)
  return (
    <div className="hair-medium" style={{ background: color }}>
      <div className="hair-bangs" style={{ background: color }} />
    </div>
  )
}

// --- Single agent at desk ---

export function AgentAtDesk({ agent }: { agent: Agent }) {
  const appearance = useMemo(() => getAppearance(agent.id), [agent.id])

  return (
    <div
      className={`desk-scene status-${agent.status} desk-variant-${appearance.deskVariant}`}
      style={{
        '--shirt-color': appearance.shirtColor,
        '--wall-hue': appearance.wallHue,
      } as React.CSSProperties}
    >
      <div className="office-wall">
        <div className="wall-panel left" />
        <div className="wall-panel right" />
        <div className="wall-clock" />
      </div>
      <div className="office-floor" />
      <div className="desk-shadow" />

      {/* Monitor */}
      <div className="monitor">
        <div className="monitor-screen">
          <ScreenContent agent={agent} variant={appearance.screenVariant} />
        </div>
        <div className="monitor-stand" />
        <div className="monitor-base" />
      </div>

      {/* Character */}
      <div className="character">
        {/* Body / Torso */}
        <div className="torso" style={{ background: appearance.shirtColor }}>
          <div className="collar" />
        </div>

        {/* Arms */}
        <div className="arms">
          <div className="arm arm-left" style={{ background: appearance.shirtColor }}>
            <div className="hand" style={{ background: appearance.skinTone }} />
          </div>
          <div className="arm arm-right typing-arm" style={{ background: appearance.shirtColor }}>
            <div className="hand" style={{ background: appearance.skinTone }} />
          </div>
        </div>

        {/* Head */}
        <div className="head" style={{ background: appearance.skinTone }}>
          <Hair style={appearance.hairStyle} color={appearance.hairColor} />
          {/* Eyes */}
          <div className="eyes">
            <div className="eye" />
            <div className="eye" />
          </div>
          {/* Glasses */}
          {appearance.hasGlasses && (
            <div className="glasses">
              <div className="lens" />
              <div className="bridge" />
              <div className="lens" />
            </div>
          )}
          {/* Mouth */}
          <div className={`mouth mouth-${agent.status}`} />
        </div>
      </div>

      {/* Desk */}
      <div className="desk">
        <div className="desk-top" />
        <div className="desk-front">
          <span />
          <span />
        </div>
        <div className="keyboard">
          <div className="key-row">
            {Array.from({ length: 8 }, (_, i) => <div key={i} className="key" />)}
          </div>
          <div className="key-row">
            {Array.from({ length: 8 }, (_, i) => <div key={i} className="key" />)}
          </div>
          <div className="key-row">
            {Array.from({ length: 6 }, (_, i) => <div key={i} className="key" />)}
          </div>
        </div>
        <div className="mouse-pad" />
        <div className="coffee-mug" />
        <div className="desk-lamp">
          <i />
        </div>
      </div>

      {/* Name tag */}
      <div className="name-tag">
        <span className="name-tag-dot" style={{ background: agent.avatar_color }} />
        {agent.name}
      </div>
    </div>
  )
}

export function AgentDeskRow({ agents, limit = 6, title = '🏢 虚拟办公室' }: { agents: Agent[]; limit?: number; title?: string }) {
  const displayAgents = agents.slice(0, limit)

  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: '1.1rem', marginBottom: 16 }}>{title}</h2>
      <div className="office-grid">
        {displayAgents.map(a => (
          <AgentAtDesk key={a.id} agent={a} />
        ))}
        {displayAgents.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">🏢</div>
            <div className="empty-text">还没有 AI 员工，去「AI 员工」页面添加吧</div>
          </div>
        )}
      </div>
    </div>
  )
}
