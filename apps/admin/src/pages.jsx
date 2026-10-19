import { useCallback, useEffect, useState } from 'react'
import { api, inr, when } from './api'

// `refreshKey` (e.g. the realtime tick) refetches the same path when it changes.
function useFetch(path, refreshKey) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => {
    if (!path) return
    api(path).then((d) => { setData(d); setError(null) }).catch(setError)
  }, [path])
  useEffect(() => { load() }, [load, refreshKey])
  return { data, error, reload: load }
}

const STATUS_TONE = {
  PENDING_ACCEPTANCE: 'blue', ACCEPTED: 'green', PREPARING: 'amber', READY: 'green', COMPLETED: 'grey',
  REJECTED: 'red', CANCELLED: 'red', APPROVED: 'green', PENDING: 'amber', SUSPENDED: 'red', PAID: 'green',
  FAILED: 'red', REFUND_PENDING: 'amber', REFUNDED: 'grey', VOID: 'grey', OPEN: 'amber', IN_PROGRESS: 'blue',
  RESOLVED: 'green', INITIATED: 'amber', SUCCEEDED: 'green',
}
const Pill = ({ s, label }) => <span className={`pill ${STATUS_TONE[s] || 'grey'}`}>{label || (s || '').replaceAll('_', ' ').toLowerCase()}</span>
const Head = ({ title, sub, children }) => (
  <div className="head"><div><h1>{title}</h1>{sub && <p>{sub}</p>}</div><div className="row">{children}</div></div>
)
const Err = ({ e }) => e ? <div className="error" role="alert">{e.message}</div> : null
const Pager = ({ data, page, setPage }) => data && data.total > data.size ? (
  <div className="pager">
    <span>{(page - 1) * data.size + 1}–{Math.min(page * data.size, data.total)} of {data.total}</span>
    <button className="btn sm ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Prev</button>
    <button className="btn sm ghost" disabled={page * data.size >= data.total} onClick={() => setPage(page + 1)}>Next ›</button>
  </div>
) : null

function Drawer({ onClose, children }) {
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onClose()
    addEventListener('keydown', esc)
    return () => removeEventListener('keydown', esc)
  }, [onClose])
  return (
    <div className="drawer-bg" onClick={onClose}>
      <div className="drawer" role="dialog" aria-modal onClick={(e) => e.stopPropagation()}>
        <button className="btn sm ghost" onClick={onClose} style={{ float: 'right' }}>Close ✕</button>
        {children}
      </div>
    </div>
  )
}

function Bars({ rows, value, label, fmt = (v) => v }) {
  const max = Math.max(1, ...rows.map((r) => r[value]))
  return (
    <div className="bars" role="img" aria-label="Bar chart">
      {rows.map((r, i) => (
        <div className="bar" key={i} title={`${r[label]}: ${fmt(r[value])}`}>
          <span>{fmt(r[value])}</span>
          <div style={{ height: `${(r[value] / max) * 80}%` }} />
          <span>{r[label]}</span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- dashboard

export function DashboardPage({ tick, go }) {
  const { data: d, error } = useFetch('/v1/admin/dashboard', tick)
  return (
    <>
      <Head title="Dashboard" sub="Last 24 hours across your colleges" />
      <Err e={error} />
      {d && (
        <>
          <div className="grid stats">
            {[
              ['Orders (24h)', d.orders_24h, `${d.completed_24h} completed`],
              ['GMV (24h)', inr(d.gmv_24h_paise), 'Completed orders, pre-tax'],
              ['Platform commission', inr(d.commission_24h_paise), 'Not net profit'],
              ['Active students', d.active_students_24h, 'Placed an order in 24h'],
              ['Live orders', d.live_orders, 'Not yet collected', () => go('orders')],
              ['Delayed', d.delayed_orders, 'Waiting for acceptance', () => go('orders'), d.delayed_orders ? 'var(--red)' : null],
              ['Pending kitchens', d.pending_kitchens, 'Awaiting approval', () => go('kitchens'), d.pending_kitchens ? 'var(--amber)' : null],
              ['Open tickets', d.open_tickets, 'Support', () => go('support')],
            ].map(([label, value, sub, onClick, color]) => (
              <div key={label} className="card stat" onClick={onClick} style={{ cursor: onClick ? 'pointer' : 'default' }}>
                <div className="label">{label}</div>
                <div className="value" style={{ color: color || undefined }}>{value}</div>
                <div className="sub">{sub}</div>
              </div>
            ))}
          </div>
          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', marginTop: 14 }}>
            <div className="card">
              <b>Completed orders · last 7 days</b>
              <Bars rows={d.series_7d.map((x) => ({ ...x, day: x.date.slice(5) }))} value="orders" label="day" />
            </div>
            <div className="card">
              <b>GMV · last 7 days</b>
              <Bars rows={d.series_7d.map((x) => ({ ...x, day: x.date.slice(5) }))} value="gmv_paise" label="day" fmt={(v) => `₹${Math.round(v / 100)}`} />
            </div>
            <div className="card">
              <b>Orders by status (24h)</b>
              <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
                {Object.entries(d.by_status_24h).length ? Object.entries(d.by_status_24h).map(([s, n]) => (
                  <div key={s} className="row" style={{ justifyContent: 'space-between' }}><Pill s={s} /><b>{n}</b></div>
                )) : <span className="muted">No orders in the last 24 hours.</span>}
              </div>
              <p className="muted" style={{ marginTop: 16 }}>{d.colleges} colleges · {d.kitchens} live kitchens · {d.students} students</p>
            </div>
          </div>
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------- orders

function OrderDrawer({ id, onClose, notify, isSuper, onChanged }) {
  const { data, error, reload } = useFetch(`/v1/admin/orders/${id}/history`)
  const cancel = async () => {
    const reason = prompt('Reason for cancelling (sent to student and kitchen):')
    if (!reason || reason.length < 3) return
    try {
      await api(`/v1/admin/orders/${id}/cancel`, { method: 'POST', body: { reason } })
      notify('Order cancelled; refund initiated if paid', 'success')
      reload(); onChanged()
    } catch (e) { notify(e.message, 'error') }
  }
  const o = data?.order
  return (
    <Drawer onClose={onClose}>
      <Err e={error} />
      {o && (
        <>
          <h2>{o.order_number}</h2>
          <p className="muted">{o.kitchen.name} · {o.student.name} (••{o.student.phone_last4}) · {when(o.created_at)}</p>
          <div className="row" style={{ margin: '12px 0' }}><Pill s={o.status} /><Pill s={o.payment_status} /><span className="muted">{o.payment_method}</span></div>
          <div className="card" style={{ marginBottom: 12 }}>
            {o.items.map((it, i) => <div key={i} className="row" style={{ justifyContent: 'space-between' }}><span>{it.quantity} × {it.name}{it.options.length ? ` (${it.options.map((x) => x.name).join(', ')})` : ''}</span><span>{inr(it.line_total_paise)}</span></div>)}
            <hr style={{ border: 0, borderTop: '1px solid var(--border)' }} />
            <div className="row" style={{ justifyContent: 'space-between' }}><span className="muted">Subtotal / GST</span><span>{inr(o.subtotal_paise)} / {inr(o.tax_paise)}</span></div>
            <div className="row" style={{ justifyContent: 'space-between' }}><b>Total</b><b>{inr(o.total_paise)}</b></div>
            {o.reason && <p className="muted">Reason: {o.reason}</p>}
          </div>
          <div className="card" style={{ marginBottom: 12 }}>
            <b>Status history</b>
            <ul className="timeline" style={{ marginTop: 10 }}>
              {data.history.map((h, i) => <li key={i}><b>{(h.to || '').replaceAll('_', ' ').toLowerCase()}</b> <span className="muted">{when(h.at)}{h.note ? ` · ${h.note}` : ''}</span></li>)}
            </ul>
          </div>
          <div className="card" style={{ marginBottom: 12 }}>
            <b>Payments</b>
            {data.payments.map((p) => <div key={p.id} className="row" style={{ justifyContent: 'space-between', marginTop: 6 }}><span>{p.method} <span className="muted">{p.provider_ref || ''}</span></span><span>{inr(p.amount_paise)} <Pill s={p.status} /></span></div>)}
            {data.refunds.map((r) => <div key={r.id} className="row" style={{ justifyContent: 'space-between', marginTop: 6 }}><span>Refund · {r.reason}</span><span>{inr(r.amount_paise)} <Pill s={r.status} /></span></div>)}
          </div>
          {isSuper && ['PENDING_ACCEPTANCE', 'ACCEPTED', 'PREPARING', 'READY'].includes(o.status) && (
            <button className="btn danger" onClick={cancel}>Cancel order & refund</button>
          )}
        </>
      )}
    </Drawer>
  )
}

export function OrdersPage({ tick, notify, isSuper }) {
  const [f, setF] = useState({ status: 'ACTIVE', college_id: '', q: '', payment_status: '' })
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(null)
  const { data: colleges } = useFetch('/v1/admin/colleges')
  const qs = new URLSearchParams({ ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), page, size: 25 })
  const { data, error, reload } = useFetch(`/v1/admin/orders?${qs}`, tick)
  const set = (k) => (e) => { setPage(1); setF({ ...f, [k]: e.target.value }) }
  return (
    <>
      <Head title="Live orders" sub="Filter by college, status and payment health. Updates in real time." />
      <div className="toolbar">
        <input placeholder="Order number e.g. CB-1024" value={f.q} onChange={set('q')} aria-label="Search order number" />
        <select value={f.status} onChange={set('status')} aria-label="Status">
          <option value="">All statuses</option><option value="ACTIVE">Active (not collected)</option><option value="DELAYED">Delayed acceptance</option>
          {['PENDING_ACCEPTANCE', 'ACCEPTED', 'PREPARING', 'READY', 'COMPLETED', 'REJECTED', 'CANCELLED'].map((s) => <option key={s} value={s}>{s.replaceAll('_', ' ').toLowerCase()}</option>)}
        </select>
        <select value={f.payment_status} onChange={set('payment_status')} aria-label="Payment status">
          <option value="">Any payment</option>{['PENDING', 'PAID', 'FAILED', 'REFUND_PENDING', 'REFUNDED', 'VOID'].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={f.college_id} onChange={set('college_id')} aria-label="College">
          <option value="">All colleges</option>{colleges?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <Err e={error} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>Order</th><th>Kitchen</th><th>Student</th><th>Items</th><th>Total</th><th>Status</th><th>Payment</th><th>Placed</th></tr></thead>
          <tbody>
            {data?.items.map((o) => (
              <tr key={o.id} className="click" onClick={() => setOpen(o.id)}>
                <td><b>{o.order_number}</b>{o.ack_overdue && <div><span className="pill red">delayed</span></div>}</td>
                <td>{o.kitchen.name}</td>
                <td>{o.student.name}<div className="muted">••{o.student.phone_last4}</div></td>
                <td className="muted" style={{ maxWidth: 240 }}>{o.items.map((i) => `${i.quantity}× ${i.name}`).join(', ')}</td>
                <td>{inr(o.total_paise)}</td>
                <td><Pill s={o.status} /></td>
                <td><Pill s={o.payment_status} /><div className="muted">{o.payment_method}</div></td>
                <td className="muted">{when(o.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.items.length && <div className="empty">No orders match these filters.</div>}
      </div>
      <Pager data={data} page={page} setPage={setPage} />
      {open && <OrderDrawer id={open} onClose={() => setOpen(null)} notify={notify} isSuper={isSuper} onChanged={reload} />}
    </>
  )
}

// ---------------------------------------------------------------- kitchens

export function KitchensPage({ notify }) {
  const [status, setStatus] = useState('PENDING')
  const [q, setQ] = useState('')
  const { data, error, reload } = useFetch(`/v1/admin/kitchens?status=${status}&q=${encodeURIComponent(q)}`)
  const act = async (k, action) => {
    let body
    if (action !== 'approve') {
      const reason = prompt(`Reason to ${action} ${k.name} (shown to the owner):`)
      if (!reason || reason.length < 3) return
      body = { reason }
    }
    try {
      await api(`/v1/admin/kitchens/${k.id}/${action}`, { method: 'POST', body })
      notify(`${k.name}: ${{ approve: 'approved', reject: 'rejected', suspend: 'suspended' }[action]}`, 'success')
      reload()
    } catch (e) { notify(e.message, 'error') }
  }
  return (
    <>
      <Head title="Kitchens" sub="Review applications, approve, reject or suspend vendors. Every action is audited." />
      <div className="toolbar">
        {['PENDING', 'APPROVED', 'REJECTED', 'SUSPENDED', ''].map((s) => (
          <button key={s} className={`btn sm ${status === s ? '' : 'ghost'}`} onClick={() => setStatus(s)}>{s ? s.toLowerCase() : 'all'}</button>
        ))}
        <input placeholder="Search kitchen" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search kitchen" />
      </div>
      <Err e={error} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>Kitchen</th><th>College</th><th>Owner</th><th>FSSAI</th><th>Status</th><th>Live</th><th>Registered</th><th></th></tr></thead>
          <tbody>
            {data?.items.map((k) => (
              <tr key={k.id}>
                <td><b>{k.emoji} {k.name}</b><div className="muted">{k.cuisine} · {k.counter_location}</div></td>
                <td>{k.college_name}</td>
                <td>{k.owner.name}<div className="muted">{k.owner.phone}</div></td>
                <td className="muted">{k.fssai_number || '—'}</td>
                <td><Pill s={k.status} />{k.status_reason && <div className="muted">{k.status_reason}</div>}</td>
                <td>{k.status === 'APPROVED' ? (k.is_open ? <span className="pill green">open</span> : <span className="pill grey">closed</span>) : '—'}</td>
                <td className="muted">{when(k.created_at)}</td>
                <td>
                  <div className="row">
                    {k.status !== 'APPROVED' && <button className="btn sm" onClick={() => act(k, 'approve')}>Approve</button>}
                    {k.status === 'PENDING' && <button className="btn sm danger" onClick={() => act(k, 'reject')}>Reject</button>}
                    {k.status === 'APPROVED' && <button className="btn sm danger" onClick={() => act(k, 'suspend')}>Suspend</button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.items.length && <div className="empty">No kitchens in this state.</div>}
      </div>
    </>
  )
}

// ---------------------------------------------------------------- colleges

const BLANK_COLLEGE = { name: '', code: '', city: '', address: '', lat: '', lng: '', contact_name: '', contact_phone: '' }

export function CollegesPage({ notify, isSuper }) {
  const { data, error, reload } = useFetch('/v1/admin/colleges')
  const [form, setForm] = useState(null)
  const save = async (e) => {
    e.preventDefault()
    const body = { ...form, lat: form.lat === '' ? null : Number(form.lat), lng: form.lng === '' ? null : Number(form.lng) }
    try {
      if (form.id) {
        const editable = ['name', 'city', 'address', 'lat', 'lng', 'contact_name', 'contact_phone', 'is_active']
        const patch = Object.fromEntries(editable.map((k) => [k, body[k]]))
        await api(`/v1/admin/colleges/${body.id}`, { method: 'PATCH', body: patch })
      } else {
        await api('/v1/admin/colleges', { method: 'POST', body })
      }
      notify('College saved', 'success')
      setForm(null)
      reload()
    } catch (err) { notify(err.message, 'error') }
  }
  const toggle = async (c) => {
    try { await api(`/v1/admin/colleges/${c.id}`, { method: 'PATCH', body: { is_active: !c.is_active } }); reload() } catch (e) { notify(e.message, 'error') }
  }
  return (
    <>
      <Head title="Colleges" sub="Campuses where CampusBite operates">
        {isSuper && <button className="btn" onClick={() => setForm(BLANK_COLLEGE)}>+ Add college</button>}
      </Head>
      <Err e={error} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>College</th><th>Code</th><th>City</th><th>Kitchens</th><th>Students</th><th>Contact</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id}>
                <td><b>{c.name}</b><div className="muted">{c.address}</div></td>
                <td>{c.code}</td><td>{c.city}</td><td>{c.kitchen_count}</td><td>{c.student_count}</td>
                <td className="muted">{c.contact_name}<br />{c.contact_phone}</td>
                <td>{c.is_active ? <span className="pill green">active</span> : <span className="pill grey">inactive</span>}</td>
                <td>{isSuper && <div className="row"><button className="btn sm ghost" onClick={() => setForm({ ...c, lat: c.lat ?? '', lng: c.lng ?? '' })}>Edit</button><button className="btn sm ghost" onClick={() => toggle(c)}>{c.is_active ? 'Deactivate' : 'Activate'}</button></div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {form && (
        <Drawer onClose={() => setForm(null)}>
          <h2>{form.id ? 'Edit college' : 'New college'}</h2>
          <form onSubmit={save} style={{ marginTop: 16 }}>
            {[['name', 'Name'], ['code', 'Short code'], ['city', 'City'], ['address', 'Address'], ['lat', 'Latitude'], ['lng', 'Longitude'], ['contact_name', 'Contact person'], ['contact_phone', 'Contact phone']].map(([k, label]) => (
              <label key={k} className="field">{label}
                <input value={form[k] ?? ''} disabled={k === 'code' && !!form.id} required={['name', 'code'].includes(k)} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              </label>
            ))}
            <button className="btn">Save</button>
          </form>
        </Drawer>
      )}
    </>
  )
}

// ---------------------------------------------------------------- users

export function UsersPage({ notify }) {
  const [q, setQ] = useState('')
  const [flagged, setFlagged] = useState('')
  const [page, setPage] = useState(1)
  const { data, error, reload } = useFetch(`/v1/admin/users?q=${encodeURIComponent(q)}&page=${page}${flagged ? `&flagged=${flagged}` : ''}`)
  const patch = async (u, body, msg) => {
    const note = prompt(`Note for audit log (${msg}):`) ?? null
    if (note === null) return
    try { await api(`/v1/admin/users/${u.id}`, { method: 'PATCH', body: { ...body, note } }); notify(msg, 'success'); reload() } catch (e) { notify(e.message, 'error') }
  }
  return (
    <>
      <Head title="Students & users" sub="Search accounts, resolve issues and flag abuse" />
      <div className="toolbar">
        <input placeholder="Phone, name or roll no." value={q} onChange={(e) => { setPage(1); setQ(e.target.value) }} aria-label="Search users" />
        <select value={flagged} onChange={(e) => { setPage(1); setFlagged(e.target.value) }} aria-label="Flag filter"><option value="">All</option><option value="true">Flagged only</option></select>
      </div>
      <Err e={error} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>User</th><th>Phone</th><th>Roll / year</th><th>Roles</th><th>Orders</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {data?.items.map((u) => (
              <tr key={u.id}>
                <td><b>{u.name || '—'}</b><div className="muted">{u.email}</div></td>
                <td>{u.phone}</td>
                <td className="muted">{u.roll_no || '—'} {u.year}</td>
                <td className="muted">{u.roles.map((r) => r.role.replace('kitchen_', 'kitchen ')).join(', ')}</td>
                <td>{u.order_count}</td>
                <td>{u.is_active ? <span className="pill green">active</span> : <span className="pill red">suspended</span>} {u.is_flagged && <span className="pill amber">flagged</span>}</td>
                <td><div className="row">
                  <button className="btn sm ghost" onClick={() => patch(u, { is_flagged: !u.is_flagged }, u.is_flagged ? 'Flag cleared' : 'User flagged')}>{u.is_flagged ? 'Unflag' : 'Flag'}</button>
                  <button className={`btn sm ${u.is_active ? 'danger' : ''}`} onClick={() => patch(u, { is_active: !u.is_active }, u.is_active ? 'User suspended' : 'User reactivated')}>{u.is_active ? 'Suspend' : 'Reactivate'}</button>
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager data={data} page={page} setPage={setPage} />
    </>
  )
}

// ---------------------------------------------------------------- payments

export function PaymentsPage({ tick }) {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const { data, error } = useFetch(`/v1/admin/payments?page=${page}${status ? `&status=${status}` : ''}`, tick)
  const { data: refunds } = useFetch('/v1/admin/refunds', tick)
  return (
    <>
      <Head title="Payments & refunds" sub="Sandbox mode — every payment traced to its order and gateway reference" />
      <div className="toolbar">
        <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value) }} aria-label="Payment status">
          <option value="">All payments</option>{['PENDING', 'PAID', 'FAILED', 'REFUNDED', 'VOID'].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <Err e={error} />
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', alignItems: 'start' }}>
        <div>
          <div className="table-wrap"><table>
            <thead><tr><th>Payment</th><th>Order</th><th>Method</th><th>Amount</th><th>Status</th></tr></thead>
            <tbody>{data?.items.map((p) => (
              <tr key={p.id}><td>#{p.id}<div className="muted">{p.provider_ref || 'no gateway ref'}</div></td><td>{p.order_number}</td><td>{p.method}</td><td>{inr(p.amount_paise)}</td><td><Pill s={p.status} /><div className="muted">{when(p.created_at)}</div></td></tr>
            ))}</tbody>
          </table></div>
          <Pager data={data} page={page} setPage={setPage} />
        </div>
        <div>
          <div className="table-wrap"><table>
            <thead><tr><th>Refund</th><th>Order</th><th>Amount</th><th>Status</th></tr></thead>
            <tbody>{refunds?.items.map((r) => (
              <tr key={r.id}><td>#{r.id}<div className="muted">{r.reason}</div></td><td>{r.order_number}</td><td>{inr(r.amount_paise)}</td><td><Pill s={r.status} /><div className="muted">{when(r.updated_at)}</div></td></tr>
            ))}</tbody>
          </table></div>
          {refunds && !refunds.items.length && <div className="empty">No refunds yet.</div>}
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- reports

export function ReportsPage({ notify }) {
  const [days, setDays] = useState(30)
  const { data, error } = useFetch(`/v1/admin/reports/kitchens?days=${days}`)
  const exportCsv = async () => {
    try {
      const res = await api(`/v1/admin/reports/orders.csv?days=${days}`, { raw: true })
      const url = URL.createObjectURL(await res.blob())
      Object.assign(document.createElement('a'), { href: url, download: `campusbite-orders-${days}d.csv` }).click()
      URL.revokeObjectURL(url)
    } catch (e) { notify(e.message, 'error') }
  }
  const totals = (data?.items || []).reduce((t, r) => ({ orders: t.orders + r.completed_orders, gmv: t.gmv + r.gmv_paise, com: t.com + r.commission_paise, pay: t.pay + r.vendor_payout_paise }), { orders: 0, gmv: 0, com: 0, pay: 0 })
  return (
    <>
      <Head title="Reports" sub="Gross order value is not business income — commission is shown separately">
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period">{[7, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}</select>
        <button className="btn ghost" onClick={exportCsv}>⬇ Export orders CSV</button>
      </Head>
      <Err e={error} />
      <div className="grid stats" style={{ marginBottom: 14 }}>
        <div className="card stat"><div className="label">Completed orders</div><div className="value">{totals.orders}</div></div>
        <div className="card stat"><div className="label">GMV</div><div className="value">{inr(totals.gmv)}</div></div>
        <div className="card stat"><div className="label">Platform commission</div><div className="value">{inr(totals.com)}</div></div>
        <div className="card stat"><div className="label">Vendor payouts</div><div className="value">{inr(totals.pay)}</div></div>
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Kitchen</th><th>College</th><th>Completed</th><th>Cancelled</th><th>GMV</th><th>Commission</th><th>Vendor payout</th></tr></thead>
        <tbody>{data?.items.map((r) => (
          <tr key={r.kitchen_id}><td><b>{r.kitchen}</b></td><td>{r.college}</td><td>{r.completed_orders}</td><td>{r.cancelled_orders}</td><td>{inr(r.gmv_paise)}</td><td>{inr(r.commission_paise)}</td><td>{inr(r.vendor_payout_paise)}</td></tr>
        ))}</tbody>
      </table></div>
    </>
  )
}

// ---------------------------------------------------------------- support

export function SupportPage({ notify }) {
  const [status, setStatus] = useState('OPEN')
  const { data, error, reload } = useFetch(`/v1/admin/support${status ? `?status=${status}` : ''}`)
  const [open, setOpen] = useState(null)
  const [note, setNote] = useState('')
  const update = async (s) => {
    try {
      await api(`/v1/admin/support/${open.id}`, { method: 'PATCH', body: { status: s, admin_note: note || null } })
      notify(`Ticket #${open.id} → ${s.toLowerCase()}`, 'success')
      setOpen(null); reload()
    } catch (e) { notify(e.message, 'error') }
  }
  return (
    <>
      <Head title="Support" sub="Student issues linked to orders" />
      <div className="toolbar">
        {['OPEN', 'IN_PROGRESS', 'RESOLVED', ''].map((s) => <button key={s} className={`btn sm ${status === s ? '' : 'ghost'}`} onClick={() => setStatus(s)}>{s ? s.replace('_', ' ').toLowerCase() : 'all'}</button>)}
      </div>
      <Err e={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>#</th><th>Student</th><th>Category</th><th>Order</th><th>Message</th><th>Status</th><th>Raised</th></tr></thead>
        <tbody>{data?.items.map((t) => (
          <tr key={t.id} className="click" onClick={() => { setOpen(t); setNote(t.admin_note || '') }}>
            <td>{t.id}</td><td>{t.user.name}<div className="muted">{t.user.phone}</div></td><td>{t.category.replace('_', ' ').toLowerCase()}</td>
            <td>{t.order_number || '—'}</td><td className="muted" style={{ maxWidth: 320 }}>{t.message}</td><td><Pill s={t.status} /></td><td className="muted">{when(t.created_at)}</td>
          </tr>
        ))}</tbody>
      </table>
      {data && !data.items.length && <div className="empty">No tickets here 🎉</div>}
      </div>
      {open && (
        <Drawer onClose={() => setOpen(null)}>
          <h2>Ticket #{open.id}</h2>
          <p className="muted">{open.user.name} · {open.user.phone} · {open.order_number || 'no order'} · {when(open.created_at)}</p>
          <div className="card" style={{ margin: '12px 0' }}>{open.message}</div>
          <label className="field">Resolution note (visible to student)
            <textarea rows={4} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="row">
            <button className="btn ghost" onClick={() => update('IN_PROGRESS')}>Mark in progress</button>
            <button className="btn" onClick={() => update('RESOLVED')}>Resolve & notify</button>
          </div>
        </Drawer>
      )}
    </>
  )
}

// ---------------------------------------------------------------- audit / flags

export function AuditPage() {
  const [page, setPage] = useState(1)
  const { data, error } = useFetch(`/v1/admin/audit-logs?page=${page}`)
  return (
    <>
      <Head title="Audit log" sub="High-impact changes: approvals, menu & price edits, refunds, exports" />
      <Err e={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead>
        <tbody>{data?.items.map((a) => (
          <tr key={a.id}><td className="muted">{when(a.created_at)}</td><td>{a.actor}</td><td><code>{a.action}</code></td><td>{a.entity} {a.entity_id}</td>
            <td className="muted" style={{ maxWidth: 380, wordBreak: 'break-word' }}>{Object.keys(a.detail || {}).length ? JSON.stringify(a.detail) : ''}</td></tr>
        ))}</tbody>
      </table></div>
      <Pager data={data} page={page} setPage={setPage} />
    </>
  )
}

export function FlagsPage({ notify }) {
  const { data, error, reload } = useFetch('/v1/admin/flags')
  const toggle = async (f) => {
    try { await api(`/v1/admin/flags/${f.key}`, { method: 'PATCH', body: { enabled: !f.enabled } }); notify(`${f.key} ${f.enabled ? 'disabled' : 'enabled'}`, 'success'); reload() } catch (e) { notify(e.message, 'error') }
  }
  return (
    <>
      <Head title="Configuration" sub="Rollout feature flags (changes are audited)" />
      <Err e={error} />
      <div className="grid" style={{ maxWidth: 640 }}>
        {data?.items.map((f) => (
          <div key={f.key} className="card row" style={{ justifyContent: 'space-between' }}>
            <div><b><code>{f.key}</code></b><div className="muted">{f.description}</div></div>
            <button className={`btn sm ${f.enabled ? '' : 'ghost'}`} onClick={() => toggle(f)} aria-pressed={f.enabled}>{f.enabled ? 'On' : 'Off'}</button>
          </div>
        ))}
      </div>
    </>
  )
}
