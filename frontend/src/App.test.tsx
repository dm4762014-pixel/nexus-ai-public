import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { api, safeDownload, safeSource, setCsrf } from './api'

const task = { id: 'task-one', prompt: 'Create a PDF report about cloud computing.', status: 'completed', plan: [{ tool: 'document', title: 'Create requested files', status: 'completed' }], answer: 'Report generated from local model content.', sources: [], artifacts: [{ id: 'artifact-one', name: 'Report.pdf', url: '/api/artifacts/artifact-one/download', size: 5000, verified: true }], warnings: [], events: [], created_at: '2026-10-21T12:00:00Z', completed_at: '2026-10-21T12:01:00Z' }
const capabilities = { model: 'qwen3:1.7b', context_size: 2048, browser_enabled: false, code_execution: false, formats: ['pdf', 'docx', 'xlsx', 'pptx'], limits: { max_active_tasks: 1 } }
let signedIn = true
let setup = false
let taskList: unknown[] = []
let specific: Record<string, unknown> = {}
let fetchMock: ReturnType<typeof vi.fn>

function respond(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }) }
beforeEach(() => {
  signedIn = true; setup = false; taskList = []; specific = {}; setCsrf('')
  fetchMock = vi.fn(async (input: string, options: RequestInit = {}) => {
    const path = input.split('?')[0]
    if (specific[path]) return respond(specific[path])
    if (path === '/api/health') return respond({ status: 'ok', setup_required: setup })
    if (path === '/api/me') return signedIn ? respond({ id: 'u1', username: 'local-user', csrf: 'test-csrf' }) : respond({ detail: 'Sign in required' }, 401)
    if (path === '/api/login' || path === '/api/setup') { signedIn = true; return respond({ ok: true }) }
    if (path === '/api/capabilities') return respond(capabilities)
    if (path === '/api/tasks' && options.method === 'POST') { taskList = [task]; return respond(task, 202) }
    if (path === '/api/tasks') return respond(taskList)
    if (path === '/api/tasks/task-one/cancel') return respond({ ...task, status: 'cancelled', completed_at: '2026-10-21T12:02:00Z' })
    if (path === '/api/tasks/task-one/retry') return respond({ ...task, id: 'task-retry', status: 'queued' })
    if (path === '/api/tasks/task-one') return respond(taskList[0] || task)
    if (path === '/api/logout') { signedIn = false; return respond({ ok: true }) }
    return respond([])
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('NEXUS workspace', () => {
  it('sets up a first account before showing the real workspace', async () => {
    setup = true; signedIn = false
    render(<App />)
    const user = userEvent.setup()
    await screen.findByText('Make this workspace yours')
    await user.type(screen.getByLabelText('Username'), 'owner')
    await user.type(screen.getByLabelText('Password'), 'a-long-test-password')
    await user.click(screen.getByRole('button', { name: 'Create local account' }))
    await screen.findByText('What can we take off your plate?')
    expect(fetchMock).toHaveBeenCalledWith('/api/setup', expect.objectContaining({ method: 'POST', body: JSON.stringify({ username: 'owner', password: 'a-long-test-password' }) }))
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    await screen.findByText('Welcome back')
    expect(screen.queryByText('Make this workspace yours')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Username'), 'owner')
    await user.type(screen.getByLabelText('Password'), 'a-long-test-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByText('What can we take off your plate?')
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/setup')).toHaveLength(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/login', expect.objectContaining({ method: 'POST' }))
  })

  it('submits a natural-language task with CSRF and shows verified downloads', async () => {
    render(<App />); const user = userEvent.setup()
    await screen.findByText('What can we take off your plate?')
    await user.type(screen.getByLabelText('Your task'), task.prompt)
    await user.click(screen.getByRole('button', { name: 'Start task' }))
    await screen.findByText('Report generated from local model content.')
    expect(screen.getByRole('link', { name: /Report.pdf/ })).toHaveAttribute('href', '/api/artifacts/artifact-one/download')
    const call = fetchMock.mock.calls.find(([path, options]) => path === '/api/tasks' && options.method === 'POST')!
    expect(call[1].headers.get('X-CSRF-Token')).toBe('test-csrf')
    expect(JSON.parse(call[1].body)).toEqual({ prompt: task.prompt, mode: 'auto', upload_ids: [] })
    expect(screen.getByText('Create requested files')).toBeInTheDocument()
  })

  it('shows exact uploaded passages safely without adding task controls', async () => {
    const saved = { ...task, upload_findings: [{ reference: 'U1', filename: 'Pilot.txt', heading: 'Handover', summary: 'The handover is Friday.', quote: '<script>untrusted upload</script> Final handover is Friday.', line_start: 40, line_end: 42, mode: 'summary' }] }
    taskList = [saved]; specific['/api/tasks/task-one'] = saved
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: task.prompt }))
    await user.click(await screen.findByText('Check uploaded evidence (1 finding)'))
    expect(screen.getByText(/Extracted lines 40–42/)).toBeInTheDocument()
    expect(screen.getByText('<script>untrusted upload</script> Final handover is Friday.')).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
    expect(screen.getByLabelText('Task mode')).toBeInTheDocument()
  })

  it('opens and focuses the exact upload citation while keeping web citations and unknown text', async () => {
    const first = { reference: 'U1', filename: 'Pilot.txt', heading: 'Budget', summary: 'The budget is set.', quote: 'The budget is set.', line_start: 1, line_end: 3, mode: 'summary' }
    const second = { ...first, reference: 'U2', heading: 'Handover', quote: 'Final handover is Friday.', line_start: 40, line_end: 42 }
    const saved = { ...task, answer: 'Budget [U1]. Handover [U2]. Unmatched [U9]. Web [1].', upload_findings: [first, second], sources: [{ number: 1, title: 'Example', url: 'https://example.com' }] }
    taskList = [saved]; specific['/api/tasks/task-one'] = saved
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: task.prompt }))
    const panel = screen.getByText('Check uploaded evidence (2 findings)').closest('details')
    expect(panel).not.toHaveAttribute('open')
    await user.click(screen.getByRole('button', { name: 'Uploaded evidence U2: Pilot.txt' }))
    expect(panel).toHaveAttribute('open')
    const passage = screen.getByRole('group', { name: '[U2] Pilot.txt' })
    expect(passage).toHaveFocus()
    expect(passage).toHaveTextContent('Final handover is Friday.')
    expect(screen.getByRole('link', { name: 'Source 1: Example' })).toHaveAttribute('href', 'https://example.com')
    expect(screen.getByText(/Unmatched \[U9\]/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Uploaded evidence U9/ })).toBeNull()
  })

  it('cancels a running task and presents retry after cancellation', async () => {
    taskList = [{ ...task, status: 'running', answer: '', completed_at: undefined, artifacts: [] }]
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: task.prompt }))
    await user.click(await screen.findByRole('button', { name: 'Cancel task' }))
    await screen.findByRole('button', { name: 'Retry task' })
    expect(fetchMock).toHaveBeenCalledWith('/api/tasks/task-one/cancel', expect.objectContaining({ method: 'POST' }))
  })

  it('offers templates as editable goals without silently starting work', async () => {
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Research a topic/ }))
    expect((screen.getByLabelText('Your task') as HTMLTextAreaElement).value).toContain('AI Agents in cybersecurity')
    expect(fetchMock.mock.calls.some(([path, options]) => path === '/api/tasks' && options.method === 'POST')).toBe(false)
  })

  it('displays code execution restrictions and actual engine configuration', async () => {
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Settings' }))
    await screen.findByText('Disabled · static validation only')
    expect(screen.getByText('2048 tokens')).toBeInTheDocument()
    expect(screen.getByText('No integrations connected')).toBeInTheDocument()
  })

  it('creates a schedule with a visible laptop availability limit', async () => {
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Scheduled tasks' }))
    expect(screen.getByText(/Execution pauses when the laptop is off or sleeping/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('What should NEXUS do?'), 'Research cybersecurity and create a PDF summary.')
    await user.click(screen.getByRole('button', { name: 'Add schedule' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/schedules', expect.objectContaining({ method: 'POST', body: JSON.stringify({ prompt: 'Research cybersecurity and create a PDF summary.', interval_minutes: 1440 }) })))
  })

  it('renders an API error without treating it as HTML', async () => {
    render(<App />); const user = userEvent.setup()
    await screen.findByText('What can we take off your plate?')
    fetchMock.mockImplementationOnce(async () => respond({ detail: '<script>bad()</script> quota exceeded' }, 429))
    await user.type(screen.getByLabelText('Your task'), 'Create a report')
    await user.click(screen.getByRole('button', { name: 'Start task' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('<script>bad()</script> quota exceeded')
    expect(document.querySelector('script')).toBeNull()
  })

  it('discards late account data after signing out and signing in again', async () => {
    const original = fetchMock.getMockImplementation()! as (input: string, options?: RequestInit) => Promise<Response>
    let resolveOld!: (response: Response) => void
    let first = true
    fetchMock.mockImplementation((input: string, options: RequestInit = {}) => {
      if (input === '/api/artifacts' && first) { first = false; return new Promise<Response>(resolve => { resolveOld = resolve }) }
      return original(input, options)
    })
    render(<App />); const user = userEvent.setup()
    await screen.findByText('What can we take off your plate?')
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    await screen.findByText('Welcome back')
    await user.type(screen.getByLabelText('Username'), 'second-user')
    await user.type(screen.getByLabelText('Password'), 'different-long-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByText('What can we take off your plate?')
    await act(async () => { resolveOld(respond([{ ...task.artifacts[0], name: 'First account private report.pdf' }])) })
    await user.click(screen.getByRole('button', { name: 'Files' }))
    expect(screen.queryByText('First account private report.pdf')).not.toBeInTheDocument()
    expect(screen.getByText('Nothing here just yet')).toBeInTheDocument()
  })

  it('links valid inline citations to retrieved HTTPS sources', async () => {
    taskList = [{ ...task, answer: 'An agent can triage an alert [1]. A missing reference stays visible [9].', sources: [{ number: 1, title: 'Retrieved source', url: 'https://example.com/evidence' }] }]
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: task.prompt }))
    const citation = await screen.findByRole('link', { name: 'Source 1: Retrieved source' })
    expect(citation).toHaveAttribute('href', 'https://example.com/evidence')
    expect(citation).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText(/A missing reference stays visible \[9\]/)).toBeInTheDocument()
  })
})

describe('Explicit task follow-ups', () => {
  beforeEach(() => { taskList = [task] })

  it('only sends prior context after choosing Follow up', async () => {
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: task.prompt }))
    await user.click(await screen.findByRole('button', { name: 'Follow up' }))
    expect(screen.getByRole('status')).toHaveTextContent('Following up on:')
    expect(screen.getByLabelText('Task mode')).toHaveValue('chat')
    expect(screen.queryByRole('option', { name: 'Research' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Your task')).toHaveFocus()
    await user.type(screen.getByLabelText('Your task'), 'Make the previous answer shorter')
    await user.click(screen.getByRole('button', { name: 'Start task' }))
    const call = fetchMock.mock.calls.find(([path, options]) => path === '/api/tasks' && options.method === 'POST')!
    expect(JSON.parse(call[1].body)).toEqual({ prompt: 'Make the previous answer shorter', mode: 'chat', upload_ids: [], parent_task_id: task.id })
    expect(screen.queryByText(/Following up on:/)).not.toBeInTheDocument()
  })

  it('removes context while keeping the editable request', async () => {
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: task.prompt }))
    await user.click(await screen.findByRole('button', { name: 'Follow up' }))
    await user.type(screen.getByLabelText('Your task'), 'An independent question')
    await user.click(screen.getByRole('button', { name: 'Remove prior context' }))
    expect(screen.getByLabelText('Your task')).toHaveValue('An independent question')
    await user.click(screen.getByRole('button', { name: 'Start task' }))
    const call = fetchMock.mock.calls.find(([path, options]) => path === '/api/tasks' && options.method === 'POST')!
    expect(JSON.parse(call[1].body)).not.toHaveProperty('parent_task_id')
  })

  it('shows bounded context and opens the previous task from history', async () => {
    const child = { ...task, prompt: 'Explain the earlier result', context: { parent_task_id: 'previous-task', turns: [{ task_id: 'previous-task', prompt: 'Prior question', answer: 'Prior answer' }], truncated: true, text_characters: 1200 } }
    taskList = [child]
    specific['/api/tasks/previous-task'] = { ...task, id: 'previous-task', prompt: 'Prior question' }
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: child.prompt }))
    expect(await screen.findByText(/Uses 1 prior result/)).toHaveTextContent('Context shortened')
    await user.click(screen.getByRole('button', { name: 'View previous task' }))
    await screen.findByText('Prior question', { selector: '.user-message p' })
    expect(fetchMock).toHaveBeenCalledWith('/api/tasks/previous-task', expect.anything())
  })

  it('clears pending context when starting fresh or changing accounts', async () => {
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: task.prompt }))
    await user.click(await screen.findByRole('button', { name: 'Follow up' }))
    await user.click(screen.getByRole('button', { name: /New task/ }))
    expect(screen.queryByText(/Following up on:/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: task.prompt }))
    await user.click(await screen.findByRole('button', { name: 'Follow up' }))
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    await screen.findByText('Welcome back')
    expect(screen.queryByText(/Following up on:/)).not.toBeInTheDocument()
  })
})

describe('API boundary', () => {
  it('only permits expected download paths and HTTPS source links', () => {
    expect(safeSource('javascript:alert(1)')).toBeUndefined()
    expect(safeSource('https://example.com')).toBe('https://example.com')
    expect(safeDownload('https://evil.example/file.pdf')).toBeUndefined()
    expect(safeDownload('/api/artifacts/../../private')).toBeUndefined()
    expect(safeDownload('/api/artifacts/id-1/download')).toBe('/api/artifacts/id-1/download')
  })

  it('presents structured FastAPI validation errors clearly', async () => {
    fetchMock.mockImplementationOnce(async () => respond({ detail: [{ loc: ['body', 'prompt'], msg: 'String should have at least 3 characters' }] }, 422))
    await expect(api('/tasks', { method: 'POST', body: '{}' })).rejects.toThrow('prompt: String should have at least 3 characters')
  })
})

describe('Browser journey previews', () => {
  it('shows authenticated previews and keeps unsafe external image URLs out', async () => {
    taskList = [{ ...task, artifacts: [
      { ...task.artifacts[0], name: 'page-1.png' },
      { id: 'unsafe', name: 'page-2.png', url: 'https://external.example/pixel', size: 20, verified: true },
    ], browser_pages: [
      { number: 1, title: 'Public evidence', url: 'https://example.com', requested_url: 'https://example.com', screenshot: 'page-1.png', reading_characters: 1000 },
      { number: 2, title: '<script>bad()</script>', url: 'javascript:alert(1)', requested_url: 'https://example.org', screenshot: 'page-2.png', reading_characters: 80 },
    ] }]
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: task.prompt }))
    expect(await screen.findByRole('region', { name: 'Browser page previews' })).toBeInTheDocument()
    await user.click(screen.getByText('Page 1: Public evidence'))
    expect(screen.getByAltText('Offline reading of Public evidence')).toHaveAttribute('src', '/api/artifacts/artifact-one/download')
    expect(document.querySelectorAll('.browser-readings img')).toHaveLength(1)
    expect(document.querySelector('script')).toBeNull()
    expect(screen.getByText('1,000 readable characters retained')).toBeInTheDocument()
  })

  it('explains the three-page workflow in the browser workspace', async () => {
    render(<App />); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Browser workspace' }))
    expect(screen.getByText(/Read up to three public HTTPS pages/)).toBeInTheDocument()
    expect(screen.getByText(/Browser screenshots are disabled/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try a two-page read' }))
    expect(screen.getByLabelText('Your task')).toHaveValue('Read https://example.com and https://www.python.org/about/ and capture the public page information.')
    expect(fetchMock.mock.calls.filter(([path, options]) => path === '/api/tasks' && options?.method === 'POST')).toHaveLength(0)
  })
})
