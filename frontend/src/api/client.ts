export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
let unauthorized: (() => void) | undefined
const pending = new Set<AbortController>()
export function onUnauthorized(handler: () => void) { unauthorized = handler }
export function cancelRequests() { pending.forEach(controller => controller.abort()); pending.clear() }
export async function api<T>(path: string, options: RequestInit = {}, timeoutMs = 15000): Promise<T> {
  const controller = new AbortController()
  pending.add(controller)
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const signal = options.signal ? AbortSignal.any([options.signal, controller.signal]) : controller.signal
  try {
    const response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', signal,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      if (response.status === 401 && !path.startsWith('/auth/')) unauthorized?.()
      throw new ApiError(response.status, typeof body.detail === 'string' ? body.detail : '请检查填写内容后重试')
    }
    return response.status === 204 ? undefined as T : await response.json() as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (signal.aborted) throw new Error('请求已取消或超时，请稍后重试')
    throw new Error('暂时无法连接服务，请检查连接后重试')
  } finally { clearTimeout(timer); pending.delete(controller) }
}
