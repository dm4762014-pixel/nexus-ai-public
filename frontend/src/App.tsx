import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, ChangeEvent } from 'react'
import {
  ArrowDownToLine, ArrowRight, ArrowUp, Blocks, Check, CheckCheck, ChevronRight,
  Circle, CircleCheck, Clock3, Code2, Command, ExternalLink, File, FileSpreadsheet,
  Files, Globe2, History, LoaderCircle, LockKeyhole, LogOut, Menu, MessageSquare,
  Paperclip, Plus, RotateCcw, Search, Settings2, ShieldCheck, Sparkles, Square,
  Terminal, Trash2, X, Zap,
} from 'lucide-react'
import { api, formatSize, safeDownload, safeSource, setCsrf } from './api'
import type { Approval, Artifact, Capabilities, Page, Schedule, ScheduleRun, Source, Task, Upload, UploadFinding, User } from './types'

const ACTIVE = ['queued', 'planning', 'running', 'awaiting_approval']
const NAV = [
  { id: 'workspace', label: 'Workspace', icon: Blocks },
  { id: 'research', label: 'Research', icon: Search },
  { id: 'files', label: 'Files', icon: Files },
  { id: 'browser', label: 'Browser workspace', icon: Globe2 },
  { id: 'code', label: 'Coding workspace', icon: Code2 },
  { id: 'schedules', label: 'Scheduled tasks', icon: Clock3 },
] as const
const DEMO = 'Research the real-world applications of AI Agents in cybersecurity. Compare reliable sources. Prepare a professional PDF report, a Word document, a PowerPoint presentation, and an Excel summary table. Include source references and give me all downloadable files.'
const TEMPLATES = [
  { icon: Search, color: 'blue', title: 'Research a topic', description: 'Find sources. Connect the evidence.', prompt: DEMO, tags: 'Research · PDF · Word · Slides · Excel' },
  { icon: FileSpreadsheet, color: 'purple', title: 'Make a study plan', description: 'Turn your subjects into a clear week.', prompt: 'Create a seven-day Excel study timetable for Python, Linux, Networking, and Cybersecurity.', tags: 'Excel · Planning' },
  { icon: Code2, color: 'green', title: 'Build something', description: 'Create code you can inspect and download.', prompt: 'Create a simple Python command-line task tracker with add, list, and complete commands. Include a README and unit tests. Package the source as a ZIP.', tags: 'Code · Static validation · ZIP' },
]
const timeLabel = (raw: string | number) => {
  const date = new Date(typeof raw === 'number' ? raw * 1000 : raw)
  return Number.isNaN(date.getTime()) ? String(raw) : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
const normalize = (task: Task): Task => ({ ...task, plan: task.plan || [], answer: task.answer || '', sources: task.sources || [], artifacts: task.artifacts || [], events: task.events || [], warnings: task.warnings || [] })

function ScheduleHistory({ runs = [], onOpen }: { runs?: ScheduleRun[]; onOpen: (id: string) => void }) {
  if (!runs.length) return <p>No recorded runs yet.</p>
  const status = (run: ScheduleRun) => run.status.charAt(0).toUpperCase() + run.status.slice(1).replaceAll('_', ' ')
  return <details className="schedule-history">
    <summary>Recent runs ({runs.length}) · {status(runs[0])}</summary>
    <ul>{runs.map(run => {
      const taskId = run.task_id
      return <li key={run.id}>
        <span>{timeLabel(run.attempted_at)} · {status(run)}</span>
        {taskId ? <button className="subtle" onClick={() => onOpen(taskId)}>Open run</button> : <span>{run.skip_reason}</span>}
      </li>
    })}</ul>
  </details>
}

function Brand({ compact = false }: { compact?: boolean }) {
  return <div className="brand"><span className="brand-mark"><Blocks size={23} strokeWidth={1.7} /></span><span>NEXUS<span className="brand-ai"> AI</span>{!compact && <small>YOUR LOCAL WORKSPACE</small>}</span></div>
}

function Auth({ setup, onLogin }: { setup: boolean; onLogin: (user: User) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      await api(setup ? '/setup' : '/login', { method: 'POST', body: JSON.stringify({ username, password }) })
      const user = await api<User>('/me'); setCsrf(user.csrf); onLogin(user)
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  return <div className="auth-shell"><div className="auth-story"><Brand /><div><span className="eyebrow"><span className="status-dot" /> LOCAL INTELLIGENCE, REAL OUTPUTS</span><h1>Give it a goal.<br /><span>Let AI do the work.</span></h1><p>From a question to a finished report. Research, create, and organize your work in one private workspace.</p><div className="auth-features"><span><ShieldCheck size={17} /> Your files stay on this machine</span><span><Zap size={17} /> Powered by your local Ollama model</span><span><Files size={17} /> Real, verified downloadable files</span></div></div><small>NEXUS AI / LOCAL WORK PLATFORM</small></div><main className="auth-panel"><div className="auth-card"><span className="auth-icon"><LockKeyhole size={25} /></span><h2>{setup ? 'Make this workspace yours' : 'Welcome back'}</h2><p>{setup ? 'Create the first local account to start working with NEXUS AI.' : 'Sign in to return to your tasks, sources, and files.'}</p><form onSubmit={submit}><label htmlFor="username">Username</label><input id="username" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={48} pattern="[a-zA-Z0-9_.-]+" autoFocus /><label htmlFor="password">Password</label><input id="password" type="password" autoComplete={setup ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} required minLength={12} maxLength={128} />{setup && <small className="input-hint">Use at least 12 characters. Store it somewhere safe.</small>}{error && <div className="error-banner" role="alert">{error}</div>}<button className="primary auth-submit" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin" /> : <ArrowRight size={17} />}{setup ? 'Create local account' : 'Sign in'}</button></form><p className="auth-note"><LockKeyhole size={13} /> Password protected. No paid API key required.</p></div></main></div>
}

function ArtifactCard({ artifact }: { artifact: Artifact }) {
  const ext = artifact.name.split('.').pop()?.toUpperCase() || 'FILE'
  return <a className="artifact-card" href={safeDownload(artifact.url)} download><span className={`file-icon ${ext === 'XLSX' ? 'green' : ext === 'PDF' ? 'red' : 'blue'}`}><File size={21} /><small>{ext}</small></span><span className="artifact-name"><strong>{artifact.name}</strong><small>{formatSize(artifact.size || 0)} {artifact.verified ? '· Structure verified' : '· Verification pending'}</small></span><ArrowDownToLine size={17} /></a>
}

function Answer({ text, sources, findings, passageId, showPassage }: {
  text: string; sources: Source[]; findings: UploadFinding[];
  passageId: (reference: string) => string; showPassage: (reference: string) => void;
}) {
  return <div className="answer-text">{text.split(/(\[(?:\d+|U\d+)\])/g).map((part, index) => {
    const uploaded = /^\[(U\d+)\]$/.exec(part)
    if (uploaded) {
      const finding = findings.find(item => item.reference === uploaded[1])
      return finding ? <button type="button" className="inline-citation upload-citation" key={index}
        aria-label={`Uploaded evidence ${finding.reference}: ${finding.filename}`}
        aria-controls={passageId(finding.reference)} onClick={() => showPassage(finding.reference)}>{part}</button> : part
    }
    const citation = /^\[(\d+)\]$/.exec(part)
    const source = citation && sources.find(item => item.number === Number(citation[1]))
    const href = source && safeSource(source.url)
    return source && href ? <a className="inline-citation" key={index} href={href} target="_blank" rel="noopener noreferrer" aria-label={`Source ${source.number}: ${source.title}`} title={source.title}>{part}</a> : part
  })}</div>
}

function Result({ task, onCancel, onRetry, onFollowup, onOpenParent, busy }: { task: Task; onCancel: () => void; onRetry: () => void; onFollowup: () => void; onOpenParent: () => void; busy: boolean }) {
  const active = ACTIVE.includes(task.status)
  const findings = task.upload_findings ?? []
  const evidenceId = useId()
  const evidenceRef = useRef<HTMLDetailsElement>(null)
  const passageId = (reference: string) => `${evidenceId}-${reference}`
  function showPassage(reference: string) {
    const panel = evidenceRef.current
    const passage = document.getElementById(passageId(reference))
    if (!panel || !passage || !panel.contains(passage)) return
    panel.open = true
    passage.focus({ preventScroll: true })
    passage.scrollIntoView?.({ block: 'center' })
  }
  return <div className="conversation">
    {task.context && <div className="context-note"><MessageSquare size={15} /><span>Uses {task.context.turns.length} prior {task.context.turns.length === 1 ? 'result' : 'results'}{task.context.truncated ? ' · Context shortened' : ''}</span><button className="subtle" onClick={onOpenParent}>View previous task</button></div>}
    <div className="user-message"><span className="message-label">YOU <span>{timeLabel(task.created_at)}</span></span><p>{task.prompt}</p></div>
    <div className="assistant-message"><div className="assistant-heading"><span className="mini-brand"><Sparkles size={16} /></span><strong>NEXUS AI</strong><span className={`status-badge ${task.status}`}>{active && <LoaderCircle size={11} className="spin" />}{task.status.replaceAll('_', ' ')}</span></div>
      {task.plan.length > 0 && <div className="inline-plan"><div className="plan-title"><Blocks size={15} /> Execution plan <small>{task.plan.filter(x => x.status === 'completed').length} / {task.plan.length}</small></div>{task.plan.map((step, index) => <div className={`plan-step ${step.status}`} key={`${step.tool}-${index}`}>{step.status === 'completed' ? <CircleCheck size={15} /> : step.status === 'running' ? <LoaderCircle size={15} className="spin" /> : step.status === 'failed' ? <X size={15} /> : <Circle size={15} />}<span>{step.title || step.tool}</span><small>{step.status?.replaceAll('_', ' ')}</small></div>)}</div>}
      {task.answer && <Answer text={task.answer} sources={task.sources} findings={findings} passageId={passageId} showPassage={showPassage} />}
      {!!findings.length && <details ref={evidenceRef} className="upload-evidence">
        <summary>Check uploaded evidence ({findings.length} {findings.length === 1 ? 'finding' : 'findings'})</summary>
        <p>Exact passages from the extracted text. Line numbers refer to extraction order, which can differ from the original page layout. AI summaries still need review.</p>
        {findings.map(finding => <div className="upload-passage" id={passageId(finding.reference)} key={finding.reference}
          tabIndex={-1} role="group" aria-labelledby={`${passageId(finding.reference)}-label`}>
          <strong id={`${passageId(finding.reference)}-label`}>[{finding.reference}] {finding.filename}</strong>
          <small>Extracted lines {finding.line_start}–{finding.line_end}{finding.mode === 'extract' ? ' · Exact extract fallback' : ''}</small>
          <blockquote>{finding.quote}</blockquote>
        </div>)}
      </details>}
      {!!task.browser_pages?.length && <section className="browser-readings" aria-label="Browser page previews"><div className="section-line"><h3>Read-only page previews</h3><span>{task.browser_pages.length} pages</span></div><p>Offline readings of the approved public pages. Scripts, forms and submissions are disabled.</p>{task.browser_pages.map(page => {
        const artifact = task.artifacts.find(item => item.name === page.screenshot)
        const preview = artifact && safeDownload(artifact.url)
        return <details key={page.number}><summary>Page {page.number}: {page.title}</summary><a href={safeSource(page.url)} target="_blank" rel="noopener noreferrer">{page.url}</a>{preview && <img src={preview} alt={`Offline reading of ${page.title}`} loading="lazy" />}<small>{page.reading_characters.toLocaleString()} readable characters retained</small></details>
      })}</section>}
      {!task.answer && active && <div className="working-line"><span className="working-dots"><i /><i /><i /></span>{task.events.at(-1)?.message || 'Preparing your task…'}</div>}
      {task.error && <div className="error-banner" role="alert">{task.error}</div>}
      {task.warnings.map((warning, i) => <div className="warning-note" key={i}><ShieldCheck size={15} /><span>{warning}</span></div>)}
      {task.artifacts.length > 0 && <div className="deliverables"><div className="section-line"><h3>Deliverables</h3><span>{task.artifacts.length} files</span></div><div className="artifact-grid">{task.artifacts.map(artifact => <ArtifactCard key={artifact.id || artifact.name} artifact={artifact} />)}</div><small className="verification-note"><CheckCheck size={13} /> File verification checks structure and content presence. Review factual claims against the sources.</small></div>}
      <div className="mobile-task-evidence"><details><summary>Sources ({task.sources.length})</summary><div className="source-list">{task.sources.length ? task.sources.map(source => <a key={source.number} href={safeSource(source.url)} target="_blank" rel="noopener noreferrer"><span className="source-number">{source.number}</span><div><strong>{source.title}</strong><small>{source.url}</small></div><ExternalLink size={13} /></a>) : <p className="muted">No web sources for this task.</p>}</div></details><details><summary>Execution history ({task.events.length})</summary><div className="activity-list">{task.events.map((event, index) => <div className="activity-entry" key={index}><span className="activity-point" /><small>{timeLabel(event.at)} · {event.tool}</small><p>{event.message}</p></div>)}</div></details></div>
      <div className="task-actions">{task.status === 'completed' && task.answer && <button className="subtle" disabled={busy} onClick={onFollowup}><MessageSquare size={14} /> Follow up</button>}{active && <button className="subtle danger" disabled={busy} onClick={onCancel}><Square size={13} /> Cancel task</button>}{['failed', 'cancelled'].includes(task.status) && <button className="subtle" disabled={busy} onClick={onRetry}><RotateCcw size={14} /> Retry task</button>}{task.completed_at && <span className="completion-time"><Check size={13} /> Finished {timeLabel(task.completed_at)}</span>}</div>
    </div>
  </div>
}

function App() {
  const [ready, setReady] = useState(false)
  const [setup, setSetup] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const [page, setPage] = useState<Page>('workspace')
  const [tasks, setTasks] = useState<Task[]>([])
  const [selected, setSelected] = useState<Task | null>(null)
  const [followup, setFollowup] = useState<Task | null>(null)
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [uploads, setUploads] = useState<Upload[]>([])
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [prompt, setPrompt] = useState('')
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('auto')
  const [attached, setAttached] = useState<Upload[]>([])
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(() => typeof window.matchMedia === 'function' && window.matchMedia('(max-width:650px)').matches)
  const [detailTab, setDetailTab] = useState('overview')
  const [schedulePrompt, setSchedulePrompt] = useState('')
  const [interval, setInterval] = useState(1440)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const uploadRef = useRef<HTMLInputElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  // Every authenticated async refresh belongs to one session generation. Late
  // responses from a previous account must never populate the next account.
  const sessionEpoch = useRef(0)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(max-width:650px)')
    const update = () => setIsMobile(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    if (!sidebarOpen || !isMobile) return
    sidebarRef.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setSidebarOpen(false); setTimeout(() => document.querySelector<HTMLButtonElement>('[aria-label="Open navigation"]')?.focus(), 0) }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [sidebarOpen, isMobile])

  const loadTasks = useCallback(async () => {
    const epoch = sessionEpoch.current
    try { const result = await api<Task[]>(`/tasks?q=${encodeURIComponent(query)}`); if (epoch === sessionEpoch.current) setTasks(result.map(normalize)) } catch (err) { if (epoch === sessionEpoch.current) throw err }
  }, [query])
  const loadCollections = useCallback(async () => {
    const epoch = sessionEpoch.current
    try {
      const [files, documents, recurring, permissions] = await Promise.all([api<Artifact[]>('/artifacts'), api<Upload[]>('/uploads'), api<Schedule[]>('/schedules'), api<Approval[]>('/approvals')])
      if (epoch === sessionEpoch.current) { setArtifacts(files); setUploads(documents); setSchedules(recurring); setApprovals(permissions) }
    } catch (err) { if (epoch === sessionEpoch.current) throw err }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function initialize() {
      try {
        const health = await api<{ setup_required: boolean }>('/health')
        if (cancelled) return
        setSetup(health.setup_required)
        if (!health.setup_required) {
          try { const profile = await api<User>('/me'); if (!cancelled) { setUser(profile); setCsrf(profile.csrf) } } catch { /* Sign-in form is expected when no session exists. */ }
        }
      } catch (err) { if (!cancelled) setError((err as Error).message) } finally { if (!cancelled) setReady(true) }
    }
    initialize(); return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!user) return
    let current = true
    api<Capabilities>('/capabilities').then(data => { if (current) setCapabilities(data) }).catch(err => { if (current) setError(err.message) })
    loadCollections().catch(err => setError(err.message))
    return () => { current = false }
  }, [user, loadCollections])

  useEffect(() => {
    if (!user) return
    loadTasks().catch(err => setError(err.message))
    const timer = window.setInterval(() => { loadTasks().catch(() => {}) }, 5000)
    return () => clearInterval(timer)
  }, [user, loadTasks])

  useEffect(() => {
    if (!user || page !== 'schedules' || busy) return
    let current = true
    const epoch = sessionEpoch.current
    const timer = window.setInterval(async () => {
      try {
        const latest = await api<Schedule[]>('/schedules')
        if (current && epoch === sessionEpoch.current) setSchedules(latest)
      } catch { /* Keep the last visible history while a refresh is unavailable. */ }
    }, 5000)
    return () => { current = false; clearInterval(timer) }
  }, [user, page, busy])

  useEffect(() => {
    if (!user || !selected || !ACTIVE.includes(selected.status)) return
    const id = selected.id
    const epoch = sessionEpoch.current
    const timer = window.setInterval(async () => {
      try {
        const task = normalize(await api<Task>(`/tasks/${id}`))
        if (epoch !== sessionEpoch.current) return
        setSelected(previous => previous?.id === id ? task : previous)
        setTasks(previous => previous.map(t => t.id === id ? task : t))
        if (!ACTIVE.includes(task.status) || task.status === 'awaiting_approval') await loadCollections()
      } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) }
    }, 1500)
    return () => clearInterval(timer)
  }, [user, selected?.id, selected?.status, loadCollections])

  async function openTask(id: string) {
    const epoch = sessionEpoch.current
    setError(''); setSidebarOpen(false); setFollowup(null); setMode('auto'); setPrompt(''); setAttached([])
    try { const task = normalize(await api<Task>(`/tasks/${id}`)); if (epoch === sessionEpoch.current) { setSelected(task); setPage('workspace') } } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) }
  }
  function newTask(nextPage: Page = 'workspace') { setFollowup(null); setSelected(null); setPage(nextPage); setPrompt(''); setAttached([]); setMode('auto'); setError(''); setSidebarOpen(false); setTimeout(() => inputRef.current?.focus(), 0) }
  function useTemplate(text: string) { setFollowup(null); setMode('auto'); setSelected(null); setPrompt(text); setTimeout(() => inputRef.current?.focus(), 0) }
  function continueTask() {
    if (!selected || selected.status !== 'completed' || !selected.answer || busy) return
    setFollowup(selected); setMode('chat'); setPrompt(''); setAttached([]); setError('')
    setTimeout(() => { inputRef.current?.focus(); inputRef.current?.scrollIntoView?.({ block: 'center' }) }, 0)
  }
  async function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!prompt.trim() || busy) return
    const epoch = sessionEpoch.current
    setBusy(true); setError('')
    const effectiveMode = mode !== 'auto' ? mode : page === 'research' ? 'research' : page === 'code' ? 'code' : page === 'browser' ? 'browser' : 'auto'
    try {
      const task = normalize(await api<Task>('/tasks', { method: 'POST', body: JSON.stringify({ prompt: prompt.trim(), mode: effectiveMode, upload_ids: attached.map(upload => upload.id), ...(followup ? { parent_task_id: followup.id } : {}) }) }))
      if (epoch !== sessionEpoch.current) return
      setSelected(task); setPage('workspace'); setFollowup(null); setMode('auto'); setPrompt(''); setAttached([]); await loadTasks()
    } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) } finally { if (epoch === sessionEpoch.current) setBusy(false) }
  }
  async function taskAction(action: 'cancel' | 'retry') {
    if (!selected) return
    const epoch = sessionEpoch.current
    setBusy(true); setError('')
    try { const task = normalize(await api<Task>(`/tasks/${selected.id}/${action}`, { method: 'POST' })); if (epoch === sessionEpoch.current) { setSelected(task); await loadTasks() } } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) } finally { if (epoch === sessionEpoch.current) setBusy(false) }
  }
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    const epoch = sessionEpoch.current
    setUploading(true); setError('')
    const body = new FormData(); body.append('file', file)
    try { const saved = await api<Upload>('/uploads', { method: 'POST', body }); if (epoch === sessionEpoch.current) { setAttached(current => [...current, saved]); await loadCollections() } } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) } finally { if (epoch === sessionEpoch.current) setUploading(false); event.target.value = '' }
  }
  async function addSchedule(event: FormEvent) {
    const epoch = sessionEpoch.current
    event.preventDefault(); setBusy(true); setError('')
    try { await api('/schedules', { method: 'POST', body: JSON.stringify({ prompt: schedulePrompt, interval_minutes: interval }) }); if (epoch === sessionEpoch.current) { setSchedulePrompt(''); await loadCollections() } } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) } finally { if (epoch === sessionEpoch.current) setBusy(false) }
  }
  async function toggleSchedule(schedule: Schedule) {
    const epoch = sessionEpoch.current
    setBusy(true); setError('')
    try {
      const state = await api<Pick<Schedule, 'enabled' | 'next_run'>>(`/schedules/${schedule.id}`, {
        method: 'PATCH', body: JSON.stringify({ enabled: !schedule.enabled }),
      })
      if (epoch === sessionEpoch.current) setSchedules(previous => previous.map(item => item.id === schedule.id ? { ...item, ...state } : item))
    } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) }
    finally { if (epoch === sessionEpoch.current) setBusy(false) }
  }
  async function removeSchedule(id: string) {
    const epoch = sessionEpoch.current
    setError('')
    try { await api(`/schedules/${id}`, { method: 'DELETE' }); if (epoch === sessionEpoch.current) await loadCollections() } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) }
  }
  async function decide(id: string, approved: boolean) {
    const epoch = sessionEpoch.current
    setBusy(true); setError('')
    try { await api(`/approvals/${id}`, { method: 'POST', body: JSON.stringify({ approved }) }); if (epoch !== sessionEpoch.current) return; await loadCollections(); if (selected) { const task = normalize(await api<Task>(`/tasks/${selected.id}`)); if (epoch === sessionEpoch.current) setSelected(task) } } catch (err) { if (epoch === sessionEpoch.current) setError((err as Error).message) } finally { if (epoch === sessionEpoch.current) setBusy(false) }
  }
  async function logout() {
    try {
      await api('/logout', { method: 'POST' }); sessionEpoch.current++
      setUser(null); setCsrf(''); setFollowup(null); setSelected(null); setTasks([]); setArtifacts([]); setUploads([]); setSchedules([]); setApprovals([]); setAttached([]); setCapabilities(null)
      setPrompt(''); setQuery(''); setSchedulePrompt(''); setMode('auto'); setPage('workspace'); setBusy(false); setUploading(false); setError(''); setSidebarOpen(false)
    } catch (err) { setError((err as Error).message) }
  }

  if (!ready) return <div className="app-loading"><Brand /><LoaderCircle size={24} className="spin" /><p>Opening your workspace…</p></div>
  if (!user) return <><Auth setup={setup} onLogin={profile => { sessionEpoch.current++; setSetup(false); setUser(profile); setError('') }} />{error && <div className="connection-error" role="alert">Cannot connect to NEXUS AI. {error}<button onClick={() => window.location.reload()}>Reconnect</button></div>}</>

  const workspacePage = ['workspace', 'research', 'browser', 'code'].includes(page)
  const pendingApprovals = approvals.filter(approval => approval.status === 'pending')
  const pageLabel = NAV.find(item => item.id === page)?.label || 'Settings'
  const titles: Record<string, { eyebrow: string; title: string; subtitle: string }> = {
    workspace: { eyebrow: 'A LITTLE LESS BUSYWORK. A LOT MORE DONE.', title: 'What can we take off your plate?', subtitle: 'Set a goal. NEXUS plans the steps, uses the tools, and brings back the results.' },
    research: { eyebrow: 'FOLLOW THE EVIDENCE', title: 'Good work starts with good sources.', subtitle: 'Search public sources, compare the evidence, and turn your findings into useful files.' },
    browser: { eyebrow: 'EXPLORE WITH BOUNDARIES', title: 'Bring the web into your workflow.', subtitle: 'Read up to three public HTTPS pages. Include their URLs, review the approval, and download page screenshots and a journey log.' },
    code: { eyebrow: 'FROM AN IDEA TO REAL FILES', title: 'Your next project starts here.', subtitle: 'Generate source files and a downloadable project. Host command execution stays disabled.' },
  }
  const title = titles[page] || titles.workspace

  return <div className="app-shell">
    {sidebarOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
    <aside ref={sidebarRef} id="workspace-navigation" className={`sidebar ${sidebarOpen ? 'open' : ''}`} inert={isMobile && !sidebarOpen} aria-hidden={isMobile && !sidebarOpen}><Brand /><button className="new-task" onClick={() => newTask()}><Plus size={17} /> New task <kbd>↵</kbd></button><nav aria-label="Main navigation">{NAV.map(item => <button key={item.id} className={`nav-item ${page === item.id ? 'selected' : ''}`} onClick={() => { if (['workspace', 'research', 'browser', 'code'].includes(item.id)) newTask(item.id); else { setPage(item.id); setSidebarOpen(false); loadCollections().catch(err => setError(err.message)) } }}><item.icon size={17} /><span>{item.label}</span>{item.id === 'schedules' && schedules.length > 0 && <small>{schedules.length}</small>}</button>)}</nav><div className="sidebar-separator" /><div className="recent-heading"><span>RECENT TASKS</span><History size={13} /></div><label className="history-search"><Search size={13} /><input aria-label="Search task history" placeholder="Search history" value={query} onChange={e => setQuery(e.target.value)} /></label><div className="recent-tasks">{tasks.length === 0 ? <p className="empty-history">{query ? 'No matching tasks.' : 'Your next idea starts a new story.'}</p> : tasks.slice(0, 30).map(task => <button key={task.id} className={`recent-task ${selected?.id === task.id ? 'active' : ''}`} onClick={() => openTask(task.id)}><MessageSquare size={14} /><span>{task.prompt}</span>{ACTIVE.includes(task.status) && <span className="task-live-dot" />}</button>)}</div><div className="sidebar-bottom"><div className="local-status"><span className="status-dot" /><span>Local workspace<small>{capabilities?.model || 'Ollama'}</small></span><ShieldCheck size={16} /></div><button className={`nav-item ${page === 'settings' ? 'selected' : ''}`} onClick={() => { setPage('settings'); setSidebarOpen(false) }}><Settings2 size={17} /> Settings</button><div className="user-row"><span className="avatar">{user.username.slice(0, 1).toUpperCase()}</span><span><strong>{user.username}</strong><small>Personal workspace</small></span><button className="icon-button" aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={16} /></button></div></div></aside>
    <div className="workspace-shell" inert={isMobile && sidebarOpen}><header className="topbar"><div><button className="icon-button mobile-menu" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}><Menu size={20} /></button><span>NEXUS AI</span><ChevronRight size={13} /><strong>{selected && workspacePage ? 'Task workspace' : pageLabel}</strong></div><span className="engine-label"><span className="status-dot" /> Local engine <span className="engine-divider">/</span> {capabilities?.model || 'Ollama'}</span></header>
      {error && <div className="global-error error-banner" role="alert"><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={15} /></button></div>}
      {pendingApprovals.length > 0 && <section className="approvals" aria-label="Approval requests">{pendingApprovals.map(approval => <div className="approval-card" key={approval.id}><ShieldCheck size={20} /><div><strong>Approval required: {approval.action.replaceAll('_', ' ')}</strong><p>{approval.detail}</p></div><button className="subtle" disabled={busy} onClick={() => decide(approval.id, false)}>Decline</button><button className="primary" disabled={busy} onClick={() => decide(approval.id, true)}>Approve</button></div>)}</section>}
      <div className={`content-layout ${selected && workspacePage ? 'has-details' : ''}`}><main className={`main-content ${selected && workspacePage ? 'task-content' : ''}`}>
        {workspacePage && <>
          {selected ? <Result key={selected.id} task={selected} onCancel={() => taskAction('cancel')} onRetry={() => taskAction('retry')} onFollowup={continueTask} onOpenParent={() => selected.context && openTask(selected.context.parent_task_id)} busy={busy} /> : <div className="welcome"><div className="welcome-symbol"><Sparkles size={27} strokeWidth={1.4} /></div><span className="eyebrow">{title.eyebrow}</span><h1>{title.title}</h1><p className="welcome-subtitle">{title.subtitle}</p></div>}
          {(page === 'browser' || mode === 'browser') && !capabilities?.browser_enabled && <div className="capability-note"><ShieldCheck size={17} /><span>Browser screenshots are disabled in this configuration. Public page retrieval is available through research.</span></div>}
          <form className={`composer ${selected ? 'followup-composer' : ''}`} onSubmit={submit}>{followup && <div className="followup-context" role="status"><MessageSquare size={16} /><div><strong>Following up on: {followup.prompt}</strong><span>Uses up to 3 prior results. Ask a question or request a document; sources are not refreshed.</span></div><button type="button" className="icon-button" aria-label="Remove prior context" onClick={() => { setFollowup(null); setMode('auto') }}><X size={15} /></button></div>}<label htmlFor="task-prompt" className="sr-only">Your task</label><textarea id="task-prompt" ref={inputRef} value={prompt} onChange={e => setPrompt(e.target.value)} placeholder={followup ? 'What would you like to do with the previous result?' : selected ? 'Start another task…' : 'Describe what you want to get done…'} rows={selected ? 2 : 3} maxLength={4000} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit() } }} />{attached.length > 0 && <div className="attachments">{attached.map(file => <span key={file.id}><File size={13} />{file.name}<button type="button" aria-label={`Remove ${file.name}`} onClick={() => setAttached(items => items.filter(item => item.id !== file.id))}><X size={13} /></button></span>)}</div>}<div className="composer-toolbar"><div><input className="sr-only" tabIndex={-1} ref={uploadRef} type="file" accept=".pdf,.docx,.xlsx,.pptx,.txt,.csv,.json" onChange={upload} /><button className="attach-button" type="button" onClick={() => uploadRef.current?.click()} disabled={uploading || attached.length >= 3} title="Attach a document">{uploading ? <LoaderCircle size={16} className="spin" /> : <Paperclip size={16} />}<span>Attach</span></button><span className="toolbar-divider" /><label className="mode-select"><Sparkles size={14} /><select aria-label="Task mode" value={mode} onChange={e => setMode(e.target.value)}>{followup ? <><option value="chat">Follow-up</option><option value="document">Document</option></> : <><option value="auto">Auto tools</option><option value="research">Research</option><option value="document">Document</option><option value="code">Code</option><option value="browser">Browser</option><option value="chat">Chat</option></>}</select></label></div><div><span className="keyboard-hint">Ctrl + Enter</span><button className="send-button" type="submit" aria-label="Start task" disabled={!prompt.trim() || busy || uploading}>{busy ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={19} />}</button></div></div></form>
          {!selected && <><div className="composer-footnote"><LockKeyhole size={11} /> Runs on your machine <span>·</span> Files verified before delivery <span>·</span> One task at a time</div>{page === 'workspace' || page === 'research' ? <section className="suggestions"><div className="section-line"><h2>A place to start</h2><span>Make it your own</span></div><div className="template-grid">{TEMPLATES.map(template => <button className="template-card" key={template.title} onClick={() => useTemplate(template.prompt)}><span className={`template-icon ${template.color}`}><template.icon size={19} /></span><ArrowRight size={15} className="template-arrow" /><strong>{template.title}</strong><p>{template.description}</p><small>{template.tags}</small></button>)}</div></section> : <div className="workspace-prompt"><button className="subtle" onClick={() => useTemplate(page === 'code' ? TEMPLATES[2].prompt : 'Read https://example.com and https://www.python.org/about/ and capture the public page information.')}><Plus size={14} />{page === 'code' ? 'Try a Python task tracker' : 'Try a two-page read'}</button></div>}<div className="welcome-footer"><span className="tiny-orbit" /><span>Ideas in. Useful work out.</span><span>NEXUS AI</span></div></>}
        </>}
        {page === 'files' && <section className="collection-page"><span className="eyebrow">YOUR WORK, ALL IN ONE PLACE</span><h1>Files</h1><p>Generated deliverables and documents you’ve added to this workspace.</p><div className="section-line"><h2>Generated files</h2><span>{artifacts.length} files</span></div>{artifacts.length ? <div className="files-list">{artifacts.map(file => <ArtifactCard key={file.id} artifact={file} />)}</div> : <div className="empty-state"><Files size={29} /><h3>Nothing here just yet</h3><p>Ask NEXUS to create a report, workbook, presentation, or code project.</p><button className="subtle" onClick={() => newTask()}><Plus size={14} /> Create a task</button></div>}<div className="section-line"><h2>Uploaded documents</h2><span>{uploads.length} documents</span></div>{uploads.length ? uploads.map(upload => <div className="upload-row" key={upload.id}><File size={20} /><div><strong>{upload.name}</strong><p>{upload.text_preview?.slice(0, 140) || 'Extracted document available for a task.'}</p></div><button className="subtle" onClick={() => { newTask(); setAttached([upload]); setPrompt(`Summarize the uploaded document ${upload.name}.`) }}>Summarize <ArrowRight size={13} /></button></div>) : <p className="muted">Attach a document to a task to see it here.</p>}</section>}
        {page === 'schedules' && <section className="collection-page"><span className="eyebrow">A LITTLE ROUTINE, AUTOMATED</span><h1>Scheduled tasks</h1><p>Repeat a workflow while NEXUS AI and your laptop are running. Execution pauses when the laptop is off or sleeping.</p><form className="schedule-form" onSubmit={addSchedule}><label htmlFor="schedule-prompt">What should NEXUS do?</label><textarea id="schedule-prompt" placeholder="Research the latest developments in cybersecurity and create a short PDF summary." value={schedulePrompt} onChange={e => setSchedulePrompt(e.target.value)} required maxLength={4000} rows={3} /><div><label htmlFor="schedule-interval">Repeat every <select id="schedule-interval" value={interval} onChange={e => setInterval(Number(e.target.value))}><option value={60}>Hour</option><option value={360}>6 hours</option><option value={1440}>Day</option><option value={10080}>Week</option></select></label><button className="primary" disabled={busy || !schedulePrompt.trim()}><Plus size={15} /> Add schedule</button></div></form><div className="section-line"><h2>Your schedules</h2><span>{schedules.length} total</span></div>{schedules.length ? schedules.map(schedule => <div className="schedule-row" key={schedule.id}><span className="schedule-clock"><Clock3 size={19} /></span><div><strong>{schedule.prompt}</strong><p>Every {schedule.interval_minutes < 1440 ? `${schedule.interval_minutes / 60} hours` : `${schedule.interval_minutes / 1440} days`} · {schedule.enabled ? `Next: ${timeLabel(schedule.next_run)}` : 'Paused'}</p><button className="subtle schedule-toggle" disabled={busy} onClick={() => toggleSchedule(schedule)}>{schedule.enabled ? 'Pause schedule' : 'Resume schedule'}</button><ScheduleHistory runs={schedule.recent_runs} onOpen={openTask} /></div><button className="icon-button" aria-label={`Remove schedule ${schedule.prompt}`} title="Remove schedule" onClick={() => removeSchedule(schedule.id)}><Trash2 size={16} /></button></div>) : <div className="empty-state"><Clock3 size={29} /><h3>No schedules yet</h3><p>Set up a recurring research summary or report above.</p></div>}</section>}
        {page === 'settings' && <section className="collection-page settings-page"><span className="eyebrow">BUILT TO RUN LOCALLY</span><h1>Workspace settings</h1><p>Current capabilities and limits for this NEXUS AI installation.</p><div className="settings-section"><h2><Zap size={17} /> Local engine</h2><dl><div><dt>AI model</dt><dd>{capabilities?.model || 'Loading…'}</dd></div><div><dt>Model context</dt><dd>{capabilities?.context_size || '—'} tokens</dd></div><div><dt>Concurrent AI tasks</dt><dd>1</dd></div><div><dt>Generated file formats</dt><dd>{capabilities?.formats?.join(', ').toUpperCase() || '—'}</dd></div></dl></div><div className="settings-section"><h2><ShieldCheck size={17} /> Permissions and isolation</h2><dl><div><dt>Browser interactions</dt><dd>{capabilities?.browser_enabled ? 'Up to 3 approved pages · read-only snapshots' : 'Disabled in this configuration'}</dd></div><div><dt>Generated code execution</dt><dd>{capabilities?.code_execution ? 'Sandbox available' : 'Disabled · static validation only'}</dd></div><div><dt>Data access</dt><dd>Account-scoped tasks and files</dd></div><div><dt>External accounts</dt><dd>No integrations connected</dd></div></dl></div>{capabilities && Object.keys(capabilities.limits || {}).length > 0 && <div className="settings-section"><h2><Settings2 size={17} /> Resource limits</h2><dl>{Object.entries(capabilities.limits).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}</dl></div>}<p className="settings-help">Engine and security settings are managed in the server environment configuration. Changes require restarting NEXUS AI.</p><button className="subtle" onClick={logout}><LogOut size={15} /> Sign out of {user.username}</button></section>}
      </main>
      {selected && workspacePage && <aside className="task-details"><div className="details-heading"><span><Blocks size={15} /> Task details</span><span className="details-id">{selected.id.slice(0, 8)}</span></div><div className="detail-tabs" role="tablist"><button role="tab" aria-selected={detailTab === 'overview'} className={detailTab === 'overview' ? 'active' : ''} onClick={() => setDetailTab('overview')}>Overview</button><button role="tab" aria-selected={detailTab === 'sources'} className={detailTab === 'sources' ? 'active' : ''} onClick={() => setDetailTab('sources')}>Sources <span>{selected.sources.length}</span></button><button role="tab" aria-selected={detailTab === 'activity'} className={detailTab === 'activity' ? 'active' : ''} onClick={() => setDetailTab('activity')}>Activity</button></div>{detailTab === 'overview' && <><div className="detail-summary"><span className={`status-badge ${selected.status}`}>{selected.status.replaceAll('_', ' ')}</span><h3>Your goal, in motion</h3><p>{selected.plan.length} planned steps · {selected.artifacts.length} deliverables</p><div className="progress-track"><span style={{ width: `${selected.plan.length ? selected.plan.filter(step => step.status === 'completed').length / selected.plan.length * 100 : 0}%` }} /></div></div><div className="details-section"><h4>TOOLS IN THIS WORKFLOW</h4>{Array.from(new Set(selected.plan.map(step => step.tool))).map(tool => <span className="tool-tag" key={tool}><Terminal size={12} />{tool.replaceAll('_', ' ')}</span>)}{!selected.plan.length && <p className="muted">The plan appears when execution starts.</p>}</div><div className="details-section"><h4>DELIVERY CHECKS</h4><p className="detail-check"><ShieldCheck size={15} /> Structure verified before download</p><p className="detail-check"><LockKeyhole size={15} /> Files belong to this account</p><p className="detail-explanation">Citation checks confirm references exist. They do not independently prove every factual claim.</p></div></>}{detailTab === 'sources' && <div className="source-list">{selected.sources.length ? selected.sources.map(source => <a key={source.number} href={safeSource(source.url)} target="_blank" rel="noopener noreferrer"><span className="source-number">{source.number}</span><div><strong>{source.title}</strong><small>{(() => { try { return new URL(source.url).hostname } catch { return source.url } })()}</small>{source.published_at && <small>{source.published_at}</small>}</div><ExternalLink size={13} /></a>) : <div className="details-empty"><Globe2 size={23} /><p>No web sources for this task yet.</p></div>}</div>}{detailTab === 'activity' && <div className="activity-list">{selected.events.length ? selected.events.map((event, index) => <div className="activity-entry" key={index}><span className="activity-point" /><small>{timeLabel(event.at)} · {event.tool}</small><p>{event.message}</p></div>) : <div className="details-empty"><History size={23} /><p>Tool activity appears here.</p></div>}</div>}<div className="details-bottom"><span className="status-dot" /> One model. One focused workflow.</div></aside>}
      </div>
    </div>
  </div>
}

export default App
