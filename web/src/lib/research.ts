import { Octokit } from 'octokit'
import yaml from 'js-yaml'

export type Operation = 'recommend' | 'feedback' | 'research' | 'review' | 'approve' | 'tasks' | 'retry'
export type Rating = 'like' | 'dislike' | 'clear'
export interface Recommendation {
  arxiv_id: string; title: string; summary: string; published_at: string; score: number
  reasons: { matched_interests: string[]; positive_feedback_terms: string[]; negative_feedback_terms: string[] }
}
export interface ResearchRun {
  id: string; operation: Operation; status: string; request_id?: string; started_at?: string
  inputs?: { question?: string }; error?: string; report?: string; report_truncated?: boolean
  elapsed_seconds?: number; used_tokens?: number
  trace?: { sources?: string[]; calls?: { tool: string; ok: boolean }[]; warnings?: string[]; pull_request?: string; recommendations?: Recommendation[]; recommendation_count?: number }
}
export interface ResearchState {
  version: number; runs: ResearchRun[]
  feedback: Record<string, { rating: 'like' | 'dislike' }>
  drafts: Record<string, { content: string; sha256: string }>
}
export interface ActionRun { id: number; run_attempt: number; display_title: string; status: string; conclusion: string | null }
export interface Snapshot { readiness: 'ready' | 'disabled' | 'outdated'; state: ResearchState; jobs: ActionRun[] }
export interface ResearchInput { operation: Operation; question?: string; paper_ids?: string; budget?: string; target?: string; feedback?: Rating; ranking?: string }
export interface Topic { id: string; query: string; enabled: boolean }
export interface RuntimeSettings {
  provider: 'deepseek' | 'openai' | 'compatible'; base_url: string; model: string; key_secret: string
  default_budget: number; max_budget: number; max_output_tokens: number; max_rounds: number; timeout_seconds: number
}
export const defaultRuntime: RuntimeSettings = { provider: 'deepseek', base_url: 'https://api.deepseek.com', model: 'deepseek-flash', key_secret: 'key', default_budget: 50000, max_budget: 1000000, max_output_tokens: 4096, max_rounds: 12, timeout_seconds: 90 }
export interface Preferences { interests: string[]; subscriptions: Topic[]; runtime: RuntimeSettings }
export function validateRuntime(value: RuntimeSettings) {
  if (!['deepseek', 'openai', 'compatible'].includes(value.provider)) throw new Error('请选择有效的供应商。')
  let url: URL
  try { url = new URL(value.base_url) } catch { throw new Error('服务地址须为 HTTPS URL。') }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error('服务地址须为不带凭据或查询参数的 HTTPS URL。')
  if (!value.model.trim() || value.model.length > 150 || /[\x00-\x1f]/.test(value.model)) throw new Error('模型名称须为 1–150 字符。')
  if (!/^[A-Za-z_][A-Za-z0-9_]{0,99}$/.test(value.key_secret) || /^GITHUB_/i.test(value.key_secret)) throw new Error('请填写有效的 Actions secret 名称，不填写密钥内容。')
  for (const [key, low, high] of [['default_budget', 1, 1000000], ['max_budget', 1, 1000000], ['max_output_tokens', 128, 32768], ['max_rounds', 1, 24], ['timeout_seconds', 10, 180]] as const) {
    if (!Number.isInteger(value[key]) || value[key] < low || value[key] > high) throw new Error(`${key} 须为 ${low}–${high} 之间的整数。`)
  }
  if (value.default_budget > value.max_budget) throw new Error('默认预算不能超过单任务上限。')
}
export const paperId = /^(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*\/\d{7})(?:v\d+)?$/i
const emptyState = (): ResearchState => ({ version: 1, runs: [], feedback: {}, drafts: {} })
function missing(error: unknown) { return (error as { status?: number })?.status === 404 }
function decode(value: string) { return new TextDecoder().decode(Uint8Array.from(atob(value.replace(/\s/g, '')), c => c.charCodeAt(0))) }
function encode(value: string) { const bytes = new TextEncoder().encode(value); let text = ''; for (const byte of bytes) text += String.fromCharCode(byte); return btoa(text) }
export function researchError(error: unknown): string {
  const status = (error as { status?: number })?.status
  if (status === 401) return 'GitHub 登录已失效，请重新连接仓库。'
  if (status === 403) return 'GitHub 拒绝访问或触发限流。请检查 Contents、Actions、Pull requests 权限，稍后刷新。'
  if (status === 409) return '配置已被其他操作更新，请重新加载后再保存。'
  if (status === 422) return 'GitHub 未接受请求，请检查工作流版本、输入和仓库权限。'
  if (status === 404) return '未找到对应资源，请检查仓库、默认分支和工作流是否已启用。'
  return error instanceof Error && !status ? error.message : '连接失败，请稍后重试。'
}
export function validateInput(input: ResearchInput) {
  const ids = (input.paper_ids || '').split(',').map(x => x.trim()).filter(Boolean)
  if (ids.length > 10 || ids.some(x => !paperId.test(x))) throw new Error('请填写最多 10 个有效 arXiv ID，用英文逗号分隔。')
  if (input.operation === 'feedback' && ids.length !== 1) throw new Error('反馈需要指定一篇论文。')
  if (['research', 'review'].includes(input.operation) && !input.question?.trim()) throw new Error('请先填写研究问题。')
  if (new TextEncoder().encode(input.question || '').length > 20000) throw new Error('问题过长，请缩小范围。')
  if (['approve', 'retry'].includes(input.operation) && !input.target) throw new Error('请选择目标草稿或任务。')
  const budget = input.budget || '50000'
  if (!/^\d+$/.test(budget) || +budget < 1 || +budget > 1000000) throw new Error('预算须为 1–1,000,000 之间的整数。')
}
export class ResearchClient {
  readonly url: string
  private ref?: string
  constructor(private api: Octokit, private owner: string, private repo: string, private onPreferencesSaved: () => void = () => {}) { this.url = `https://github.com/${owner}/${repo}` }
  private get params() { return { owner: this.owner, repo: this.repo } }
  private async branch() {
    if (!this.ref) this.ref = (await this.api.rest.repos.get(this.params)).data.default_branch
    return this.ref!
  }
  private async file(path: string, ref: string) {
    const { data } = await this.api.rest.repos.getContent({ ...this.params, path, ref })
    if (Array.isArray(data) || data.type !== 'file' || !('content' in data) || data.encoding !== 'base64') throw new Error('仓库文件格式不受支持。')
    return { content: decode(data.content), sha: data.sha }
  }
  private async state(): Promise<ResearchState> {
    let content: string
    try { content = (await this.file('data/agent-state.json', 'agent-state')).content }
    catch (error) { if (missing(error)) return emptyState(); throw error }
    let data: ResearchState
    try { data = JSON.parse(content) } catch { throw new Error('研究状态无法解析，请检查 agent-state 分支。') }
    if (data.version !== 1 || !Array.isArray(data.runs) || !data.feedback || typeof data.feedback !== 'object') throw new Error('研究状态格式不正确，请检查 agent-state 分支。')
    if (data.runs.some(r => !r || typeof r.id !== 'string' || typeof r.operation !== 'string' || typeof r.status !== 'string')) throw new Error('研究任务记录格式不正确。')
    return { ...data, drafts: data.drafts || {} }
  }
  async snapshot(): Promise<Snapshot> {
    const branch = await this.branch()
    const [state, workflow] = await Promise.all([this.state(), this.api.rest.actions.getWorkflow({ ...this.params, workflow_id: 'research-agent.yml' }).then(r => r.data).catch(e => { if (missing(e)) return null; throw e })])
    if (!workflow) return { readiness: 'disabled', state, jobs: [] }
    const jobs = (await this.api.rest.actions.listWorkflowRuns({ ...this.params, workflow_id: 'research-agent.yml', branch, per_page: 30 })).data.workflow_runs as ActionRun[]
    if (workflow.state !== 'active') return { readiness: 'disabled', state, jobs }
    try {
      const source = await this.file('.github/workflows/research-agent.yml', branch)
      return { readiness: source.content.includes('steps.settings.outputs.secret_name') ? 'ready' : 'outdated', state, jobs }
    } catch (error) { if (missing(error)) return { readiness: 'disabled', state, jobs }; throw error }
  }
  async dispatch(input: ResearchInput, requestId: string) {
    validateInput(input)
    await this.api.rest.actions.createWorkflowDispatch({ ...this.params, workflow_id: 'research-agent.yml', ref: await this.branch(), inputs: { ...input, request_id: requestId } })
  }
  async cancel(id: number) { await this.api.rest.actions.cancelWorkflowRun({ ...this.params, run_id: id }) }
  async preferences(): Promise<{ value: Preferences; sha: string; content: string }> {
    const file = await this.file('config.yaml', await this.branch())
    const config = yaml.load(file.content) as { agent?: Partial<Preferences> }
    if (!config || typeof config !== 'object' || Array.isArray(config)) throw new Error('config.yaml 须为配置对象。')
    return { ...file, value: { interests: config.agent?.interests || [], subscriptions: config.agent?.subscriptions || [], runtime: { ...defaultRuntime, ...(config.agent?.runtime?.provider === 'openai' ? { base_url: 'https://api.openai.com/v1', model: 'gpt-4.1-mini', key_secret: 'OPENAI_API_KEY' } : {}), ...config.agent?.runtime } } }
  }
  async savePreferences(value: Preferences, original: { sha: string; content: string }) {
    validateRuntime(value.runtime)
    if (value.interests.length > 30 || value.interests.some(x => !x.trim() || x.length > 100)) throw new Error('最多 30 个兴趣短语，每个 1–100 字符。')
    if (value.subscriptions.length > 10 || new Set(value.subscriptions.map(x => x.id)).size !== value.subscriptions.length || value.subscriptions.some(x => !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,39}$/.test(x.id) || !x.query.trim() || x.query.length > 160 || /["\\\x00-\x1f]/.test(x.query))) throw new Error('最多 10 个主题；ID 须唯一且仅含字母、数字、连字符、下划线；查询为 1–160 字符的普通短语。')
    const config = yaml.load(original.content) as Record<string, unknown>
    const previous = config.agent && typeof config.agent === 'object' ? config.agent : {}
    config.agent = { ...previous, ...value }
    await this.api.rest.repos.createOrUpdateFileContents({ ...this.params, branch: await this.branch(), path: 'config.yaml', sha: original.sha, content: encode(yaml.dump(config, { lineWidth: -1 })), message: 'feat:更新研究配置' })
    this.onPreferencesSaved()
  }
}
