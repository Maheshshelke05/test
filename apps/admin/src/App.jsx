import { useCallback, useEffect, useRef, useState } from 'react'
import { api, accessToken, API_URL, hasSession, saveTokens, setExpiredHandler } from './api'
import {
  AuditPage, CollegesPage, DashboardPage, FlagsPage, KitchensPage, OrdersPage, PaymentsPage, ReportsPage, SupportPage, UsersPage,
} from './pages'

const NAV = [
  ['dashboard', '📊', 'Dashboard'],
  ['orders', '🧾', 'Live orders'],
  ['kitchens', '🍳', 'Kitchens'],
  ['colleges', '🏫', 'Colleges'],
  ['users', '👥', 'Students & users'],
  ['payments', '💳', 'Payments & refunds', 'super'],
  ['reports', '📈', 'Reports'],
  ['support', '💬', 'Support'],
  ['audit', '🛡️', 'Audit log', 'super'],
  ['flags', '⚙️', 'Configuration', 'super'],
]
const PAGES = {
  dashboard: DashboardPage, orders: OrdersPage, kitchens: KitchensPage, colleges: CollegesPage, users: UsersPage,
  payments: PaymentsPage, reports: ReportsPage, support: SupportPage, audit: AuditPage, flags: FlagsPage,
}

function Login({ onDone }) {
  const [phone, setPhone] = useState('9000000000')
  const [code, setCode] = useState('')
  const [step, setStep] = useState('phone')
  const [hint, setHint] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (step === 'phone') {
        const r = await api('/v1/auth/otp/request', { method: 'POST', body: { phone } })
        setHint(r.dev_code)
        setStep('otp')
      } else {
        const r = await api('/v1/auth/otp/verify', { method: 'POST', body: { phone, code } })
        const admin = r.user.roles.some((x) => x.role === 'super_admin' || x.role === 'college_admin')
        if (!admin) throw new Error('This account does not have admin access.')
        saveTokens({ access_token: r.access_token, refresh_token: r.refresh_token })
        onDone(r.user)
      }
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  return (
    <div className="login">
      <form className="card" onSubmit={submit}>
        <h1>campusbite</h1>
        <p className="muted" style={{ marginTop: 4, marginBottom: 24 }}>Operations console · admins only</p>
        {error && <div className="error" role="alert">{error}</div>}
        {step === 'phone' ? (
          <label className="field">Admin mobile number
            <input value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))} maxLength={10} autoFocus />
          </label>
        ) : (
          <label className="field">OTP sent to +91 {phone}
            <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} maxLength={6} autoFocus style={{ letterSpacing: 6, fontSize: 20 }} />
            {hint && <span className="muted">Local test mode — OTP is <b>{hint}</b></span>}
          </label>
        )}
        <button className="btn" style={{ width: '100%' }} disabled={busy}>{step === 'phone' ? 'Send OTP' : 'Sign in'}</button>
        <p className="muted" style={{ marginTop: 16 }}>Demo: super admin 9000000000 · college admin 9000000001</p>
      </form>
    </div>
  )
}

export default function App() {
  const [me, setMe] = useState(null)
  const [booting, setBooting] = useState(hasSession())
  const [page, setPage] = useState(() => location.hash.slice(1) || 'dashboard')
  const [toast, setToast] = useState(null)
  const [live, setLive] = useState(false)
  const [tick, setTick] = useState(0)
  const [counts, setCounts] = useState({})
  const toastTimer = useRef()

  const notify = useCallback((text, kind = 'info') => {
    clearTimeout(toastTimer.current)
    setToast({ text, kind })
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }, [])

  useEffect(() => {
    setExpiredHandler(() => setMe(null))
    if (hasSession()) api('/v1/auth/me').then(setMe).catch(() => saveTokens(null)).finally(() => setBooting(false))
  }, [])
  useEffect(() => { location.hash = page }, [page])

  const isSuper = me?.roles.some((r) => r.role === 'super_admin')
  const meId = me?.id

  // Live channel: any order event bumps `tick` so open pages refetch.
  useEffect(() => {
    if (!meId) return
    let ws, stop = false, delay = 1000
    const open = () => {
      if (stop) return // a reconnect timer can fire after logout/unmount
      // The token goes in the first frame, not the URL, so it never lands in server logs.
      ws = new WebSocket(`${API_URL.replace(/^http/, 'ws')}/v1/realtime`)
      ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: accessToken() }))
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data)
        if (m.type === 'hello') { setLive(true); delay = 1000 }
        if (m.type === 'order_updated' || m.type === 'ack_overdue') setTick((t) => t + 1)
      }
      ws.onclose = () => { setLive(false); if (!stop) setTimeout(open, (delay = Math.min(delay * 2, 15000))) }
    }
    open()
    return () => { stop = true; ws?.close() }
  }, [meId])

  useEffect(() => {
    if (!meId) return
    api('/v1/admin/dashboard').then((d) => setCounts({ kitchens: d.pending_kitchens, support: d.open_tickets, orders: d.delayed_orders })).catch(() => {})
  }, [meId, tick, page])

  if (booting) return <div className="login"><div style={{ color: '#fff' }}>Loading…</div></div>
  if (!me) return <Login onDone={setMe} />

  const Page = PAGES[page] || DashboardPage
  return (
    <div className="layout">
      <aside className="side">
        <div className="brand">campusbite<small>Operations console</small></div>
        <nav className="nav" aria-label="Main">
          {NAV.filter(([, , , need]) => !need || isSuper).map(([id, icon, label]) => (
            <button key={id} className={page === id ? 'on' : ''} onClick={() => setPage(id)} aria-current={page === id ? 'page' : undefined}>
              <span aria-hidden>{icon}</span>{label}
              {counts[id] ? <span className="count" aria-label={`${counts[id]} need attention`}>{counts[id]}</span> : null}
            </button>
          ))}
        </nav>
        <div className="side-foot">
          <div>{live ? <><span className="live-dot" />Live</> : 'Reconnecting…'}</div>
          <div style={{ marginTop: 6 }}>{me.name} · {isSuper ? 'Super admin' : 'College admin'}</div>
          <button className="btn sm ghost" style={{ marginTop: 10 }} onClick={async () => { await api('/v1/auth/logout', { method: 'POST' }).catch(() => {}); saveTokens(null); setMe(null) }}>Log out</button>
        </div>
      </aside>
      <main className="main">
        <Page notify={notify} tick={tick} isSuper={isSuper} go={setPage} />
      </main>
      {toast && <div className={`toast ${toast.kind}`} role="status">{toast.text}</div>}
    </div>
  )
}
