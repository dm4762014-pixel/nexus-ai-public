let csrf = ''
export function setCsrf(token: string) { csrf = token }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (options.method && options.method !== 'GET' && csrf) headers.set('X-CSRF-Token', csrf)
  const response = await fetch(`/api${path}`, { credentials: 'same-origin', ...options, headers })
  let body: unknown
  try { body = await response.json() } catch { throw new Error(`The server returned an unreadable response (${response.status}).`) }
  if (!response.ok) {
    const detail = (body as { detail?: unknown }).detail
    const validation = Array.isArray(detail) ? detail.map((item: { msg?: string; loc?: string[] }) => `${(item.loc || []).filter(field => field !== 'body').join('.')}: ${item.msg || 'Invalid input'}`).join('; ') : ''
    throw new Error(typeof detail === 'string' ? detail : validation || `Request failed (${response.status}).`)
  }
  return body as T
}

export function safeSource(url: string) { try { return new URL(url).protocol === 'https:' ? url : undefined } catch { return undefined } }
export function safeDownload(url: string) { return /^\/api\/(?:artifacts\/[a-zA-Z0-9_-]+(?:\/download)?|download\/[a-zA-Z0-9_-]+\.[a-zA-Z0-9]+)$/.test(url) ? url : undefined }
export function formatSize(bytes: number) { return bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB` }
