import { useEffect, useMemo, useRef, useState } from 'react'
import { GithubClient } from '@/lib/github'
import { researchError, defaultRuntime, type RuntimeSettings, type Snapshot, type Operation, type ResearchInput, type Preferences } from '@/lib/research'
import { Button } from '@/components/ui/button'
import { MarkdownViewer } from '@/components/MarkdownViewer'

const labels: Record<string, string> = { recommend: '论文推荐', research: '研究问答', review: '生成综述', feedback: '论文反馈', approve: '保存笔记', retry: '重试', tasks: '任务中心' }
const field = 'w-full rounded-md border bg-background p-2 text-sm'
export function ResearchView({ client, lang }: { client: GithubClient; lang: string }) {
  const api = useMemo(() => client.researchClient(), [client])
  const [snapshot, setSnapshot] = useState<Snapshot>()
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const mounted = useRef(true)
  const refreshEpoch = useRef(0)
  const preferencesEpoch = useRef(0)
  const [selected, setSelected] = useState('')
  const [operation, setOperation] = useState<Operation>('research')
  const [question, setQuestion] = useState('')
  const [ids, setIds] = useState('')
  const [budget, setBudget] = useState('50000')
  const [pending, setPending] = useState(() => { try { return sessionStorage.getItem(`research-pending:${api.url}`) || '' } catch { return '' } })
  useEffect(() => { try { if (pending) sessionStorage.setItem(`research-pending:${api.url}`, pending); else sessionStorage.removeItem(`research-pending:${api.url}`) } catch { /* Storage may be disabled. */ } }, [pending, api])
  const [confirm, setConfirm] = useState('')
  const [settings, setSettings] = useState(false)
  const [preferences, setPreferences] = useState<Preferences>({ interests: [], subscriptions: [], runtime: defaultRuntime })
  const [runtime, setRuntime] = useState(defaultRuntime)
  const budgetTouched = useRef(false)
  const [original, setOriginal] = useState<{ sha: string; content: string }>()
  async function refresh() {
    const epoch = ++refreshEpoch.current
    try { const value = await api.snapshot(); if (mounted.current && epoch === refreshEpoch.current) { setSnapshot(value); setError('') } }
    catch (e) { if (mounted.current && epoch === refreshEpoch.current) setError(researchError(e)) }
  }
  useEffect(() => {
    mounted.current = true
    void refresh()
    const preferenceRequest = ++preferencesEpoch.current
    api.preferences().then(result => {
      if (mounted.current && preferenceRequest === preferencesEpoch.current) {
        setPreferences(result.value)
        setRuntime(result.value.runtime)
        if (!budgetTouched.current) setBudget(String(result.value.runtime.default_budget))
      }
    }).catch(() => { /* The settings panel exposes configuration errors on demand. */ })
    const timer = setInterval(() => { if (!document.hidden) void refresh() }, 15000)
    return () => { mounted.current = false; refreshEpoch.current++; preferencesEpoch.current++; clearInterval(timer) }
  }, [api])
  const runs = snapshot?.state.runs.slice().reverse() || []
  const run = runs.find(r => r.id === selected) || runs[0]
  const job = snapshot?.jobs.find(j => run && `${j.id}-${j.run_attempt}` === run.id)
  const linked = snapshot?.jobs.find(j => pending && j.display_title.includes(pending))
  useEffect(() => {
    if (!pending || !snapshot) return
    const result = snapshot.state.runs.find(r => r.request_id === pending)
    if (result) setSelected(result.id)
    if (result && result.status !== 'running' || linked?.status === 'completed') { setPending(''); setNotice(linked?.conclusion && linked.conclusion !== 'success' ? '任务未成功完成，请打开 Actions 查看失败步骤；已保存的任务可重试。' : result && result.status !== 'running' ? '任务已结束，结果与状态已更新。' : '运行已结束，研究结果尚未保存，请打开 Actions 查看详情。') }
  }, [snapshot, pending, linked])
  async function submit(input: ResearchInput) {
    if (lock.current || pending) return
    lock.current = true; setBusy(true); setError(''); setNotice('')
    try { if (input.budget && +input.budget > runtime.max_budget) throw new Error(`预算超过配置上限 ${runtime.max_budget}。`); const requestId = crypto.randomUUID(); await api.dispatch(input, requestId); setPending(requestId); setNotice('请求已发送，等待 GitHub 排队执行。'); await refresh() }
    catch (e) { setError(researchError(e)) }
    finally { lock.current = false; setBusy(false) }
  }
  const disabled = busy || settings || !!pending || snapshot?.readiness !== 'ready'
  function download() {
    if (!run?.report) return
    const url = URL.createObjectURL(new Blob([run.report], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `research-${run.id}.md`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  async function openSettings() {
    const preferenceRequest = ++preferencesEpoch.current
    setSettings(true); setOriginal(undefined)
    try {
      const result = await api.preferences()
      if (!mounted.current || preferenceRequest !== preferencesEpoch.current) return
      setPreferences(result.value); setOriginal(result); setRuntime(result.value.runtime)
      if (!budgetTouched.current) setBudget(String(result.value.runtime.default_budget))
    } catch (e) {
      if (mounted.current && preferenceRequest === preferencesEpoch.current) setError(researchError(e))
    }
  }
  return <div className="h-full overflow-auto"><div className="mx-auto max-w-6xl space-y-5 p-4 md:p-8">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-semibold">{lang === 'en' ? 'Research workspace' : '研究助手'}</h1><p className="mt-1 text-sm text-muted-foreground">从论文发现到研究笔记，让每一步都有依据。</p></div><div className="flex gap-2"><Button variant="outline" onClick={openSettings}>研究配置</Button><Button variant="outline" disabled={disabled} onClick={() => submit({ operation: 'research', question: '这是模型连接测试。请不要调用工具，只回复：连接成功。', budget: String(Math.min(20000, runtime.default_budget)) })}>测试模型连接</Button><Button variant="outline" onClick={refresh}>刷新状态</Button></div></div>
    {error && <div role="alert" className="rounded-lg border border-destructive p-3 text-sm text-destructive">{error}</div>}
    {notice && <p role="status" className="rounded-lg bg-muted p-3 text-sm">{notice}</p>}
    {!snapshot && !error && <p role="status">正在读取研究空间…</p>}
    {snapshot && snapshot.readiness !== 'ready' && <div className="space-y-2 rounded-lg border p-4 text-sm"><strong>{snapshot.readiness === 'outdated' ? '研究工作流需要更新' : '研究工作流尚未启用'}</strong><p>将仓库中的 .github/workflow-templates/research-agent.yml 复制到 .github/workflows/ 并合入默认分支；按研究配置中的密钥名称设置 Actions secret，允许 Actions 写入内容和创建 PR。网页令牌还需 Actions 读写权限。</p><p>研究问题与取得的资料会发送给模型，任务结果存于仓库。启用后点击刷新即可开始；定时推荐仍需单独开启。</p><a className="underline" href={`${api.url}/settings/actions`} target="_blank" rel="noreferrer">打开仓库 Actions 设置 ↗</a></div>}
    {settings && <section className="space-y-3 rounded-xl border p-4"><h2 className="font-semibold">模型、预算与研究偏好</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">模型供应商<select aria-label="模型供应商" className={`${field} mt-1`} disabled={!original} value={preferences.runtime.provider} onChange={e => { const provider = e.target.value as RuntimeSettings['provider']; setPreferences({ ...preferences, runtime: { ...preferences.runtime, provider, base_url: provider === 'openai' ? 'https://api.openai.com/v1' : provider === 'deepseek' ? 'https://api.deepseek.com' : '', model: provider === 'openai' ? 'gpt-4.1-mini' : provider === 'deepseek' ? 'deepseek-flash' : '', key_secret: provider === 'openai' ? 'OPENAI_API_KEY' : provider === 'deepseek' ? 'key' : 'MODEL_API_KEY' } }) }}><option value="deepseek">DeepSeek</option><option value="openai">OpenAI</option><option value="compatible">OpenAI 兼容服务</option></select></label>
        {(['base_url', 'model', 'key_secret'] as const).map(key => <label key={key} className="text-sm">{{ base_url: 'API 基础地址', model: '模型名称', key_secret: 'Actions 密钥名称' }[key]}<input aria-label={key} disabled={!original} className={`${field} mt-1`} value={preferences.runtime[key]} onChange={e => setPreferences({ ...preferences, runtime: { ...preferences.runtime, [key]: e.target.value } })}/></label>)}
        {(['default_budget', 'max_budget'] as const).map(key => <label key={key} className="text-sm">{key === 'default_budget' ? '默认任务预算（tokens）' : '单任务预算上限（tokens）'}<input aria-label={key} type="number" min="1" max="1000000" disabled={!original} className={`${field} mt-1`} value={preferences.runtime[key]} onChange={e => setPreferences({ ...preferences, runtime: { ...preferences.runtime, [key]: Number(e.target.value) } })}/></label>)}
      </div>
      <p className="text-xs text-muted-foreground">密钥保存在 GitHub Actions secrets，网页只保存名称。兼容服务须支持 Chat Completions、工具调用和 JSON 输出；基础地址包含 /v1 时请保留，勿填写 /chat/completions。</p>
      <a className="inline-block text-sm underline" href={`${api.url}/settings/secrets/actions`} target="_blank" rel="noreferrer">配置供应商密钥 ↗</a>
      <details className="space-y-2 text-sm"><summary className="cursor-pointer">高级运行参数</summary><div className="grid gap-3 pt-3 sm:grid-cols-3">{(['max_output_tokens', 'max_rounds', 'timeout_seconds'] as const).map(key => <label key={key}>{{ max_output_tokens: '单次最大输出 tokens', max_rounds: '最大工具轮数', timeout_seconds: '请求超时（秒）' }[key]}<input aria-label={key} className={`${field} mt-1`} type="number" disabled={!original} value={preferences.runtime[key]} onChange={e => setPreferences({ ...preferences, runtime: { ...preferences.runtime, [key]: Number(e.target.value) } })}/></label>)}</div></details>
      <h3 className="pt-2 font-medium">兴趣与主题订阅</h3><label className="block text-sm">兴趣短语，每行一个<textarea aria-label="兴趣短语" className={`${field} mt-2 min-h-24`} disabled={!original} value={preferences.interests.join('\n')} onChange={e => setPreferences({ ...preferences, interests: e.target.value.split('\n') })}/></label>
      <p className="text-xs text-muted-foreground">订阅查询使用普通短语，不填写 arXiv 查询表达式。首次扫描历史记录，每次最多 300 条／主题。</p>
      {preferences.subscriptions.map((topic, index) => <div key={index} className="flex flex-wrap gap-2"><input aria-label={`主题 ${index + 1} ID`} className={`${field} sm:!w-36`} value={topic.id} onChange={e => setPreferences({ ...preferences, subscriptions: preferences.subscriptions.map((t, i) => i === index ? { ...t, id: e.target.value } : t) })}/><input aria-label={`主题 ${index + 1} 查询`} className={`${field} sm:!w-64`} value={topic.query} onChange={e => setPreferences({ ...preferences, subscriptions: preferences.subscriptions.map((t, i) => i === index ? { ...t, query: e.target.value } : t) })}/><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={topic.enabled} onChange={e => setPreferences({ ...preferences, subscriptions: preferences.subscriptions.map((t, i) => i === index ? { ...t, enabled: e.target.checked } : t) })}/>启用</label><Button variant="ghost" onClick={() => setPreferences({ ...preferences, subscriptions: preferences.subscriptions.filter((_, i) => i !== index) })}>删除</Button></div>)}
      <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={!original || preferences.subscriptions.length >= 10} onClick={() => setPreferences({ ...preferences, subscriptions: [...preferences.subscriptions, { id: '', query: '', enabled: true }] })}>添加主题</Button><Button disabled={!original || busy} onClick={async () => { if (!original) return; setBusy(true); try { await api.savePreferences({ ...preferences, interests: preferences.interests.map(s => s.trim()).filter(Boolean) }, original); setError(''); setRuntime(preferences.runtime); setBudget(String(preferences.runtime.default_budget)); budgetTouched.current = false; setNotice('研究配置已保存，下次运行生效。'); setSettings(false) } catch (e) { setError(researchError(e)) } finally { setBusy(false) } }}>保存到仓库</Button><Button variant="ghost" onClick={() => setSettings(false)}>关闭</Button></div></section>}
    <p className="text-xs text-muted-foreground">当前模型：{runtime.provider} / {runtime.model} · 单任务上限 {runtime.max_budget.toLocaleString()} tokens</p>
    <form className="space-y-3 rounded-xl border bg-card p-5" onSubmit={e => { e.preventDefault(); void submit(operation === 'recommend' ? { operation } : { operation, question, paper_ids: ids, budget }) }}>
      <div className="flex flex-wrap gap-2">{(['research', 'review', 'recommend'] as Operation[]).map(op => <Button type="button" key={op} variant={operation === op ? 'secondary' : 'ghost'} onClick={() => setOperation(op)}>{labels[op]}</Button>)}</div>
      {operation !== 'recommend' && <><label className="block text-sm">研究问题<textarea aria-label="研究问题" className={`${field} mt-2 min-h-28`} placeholder="例如：比较多智能体协作中的任务分解方法，说明证据、差异与局限。" value={question} onChange={e => setQuestion(e.target.value)}/></label><div className="grid gap-3 sm:grid-cols-2"><label className="text-sm">指定论文（可选）<input aria-label="指定论文" className={`${field} mt-1`} placeholder="arXiv ID，英文逗号分隔，最多 10 篇" value={ids} onChange={e => setIds(e.target.value)}/></label><label className="text-sm">本次累计 token 预算<input aria-label="token 预算" type="number" min="1" max="1000000" step="1" className={`${field} mt-1`} value={budget} onChange={e => { budgetTouched.current = true; setBudget(e.target.value) }}/></label></div></>}
      <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-muted-foreground">{operation === 'recommend' ? '根据兴趣、反馈与独立主题推荐，不调用模型。' : '仅使用提供的工具研究；综述保存前需要人工核验。'}</p><Button type="submit" disabled={disabled}>{busy ? '发送中…' : `开始${labels[operation]}`}</Button></div>
    </form>
    {pending && <div role="status" className="flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm"><span>{linked ? `任务${linked.status === 'queued' ? '排队中' : '执行中'}` : '等待任务出现，通常需要数秒；页面每 15 秒刷新。'}</span><a className="underline" href={linked ? `${api.url}/actions/runs/${linked.id}` : `${api.url}/actions`} target="_blank" rel="noreferrer">查看 Actions ↗</a>{linked && <Button variant="outline" onClick={async () => { try { await api.cancel(linked.id); setNotice('已请求取消，等待 GitHub 确认。'); await refresh() } catch (e) { setError(researchError(e)) } }}>请求取消</Button>}<Button variant="ghost" onClick={() => { setPending(''); setNotice('已停止跟踪；已发送任务仍可在 Actions 查看，请勿重复发送。') }}>停止跟踪</Button></div>}
    <div className="grid items-start gap-4 lg:grid-cols-[250px_minmax(0,1fr)]"><aside className="rounded-xl border p-3"><h2 className="mb-3 font-semibold">最近任务</h2>{!runs.length && <p className="p-2 text-sm text-muted-foreground">还没有研究任务。配置兴趣后，可先获取论文推荐。</p>}<div className="max-h-96 space-y-1 overflow-auto">{runs.map(r => <button key={r.id} className={`w-full rounded-md p-3 text-left text-sm ${run?.id === r.id ? 'bg-secondary' : 'hover:bg-muted'}`} onClick={() => { setSelected(r.id); setConfirm('') }}><span className="block font-medium">{labels[r.operation] || r.operation} · {r.status}</span><span className="mt-1 block truncate text-xs text-muted-foreground">{r.inputs?.question || r.id}</span></button>)}</div></aside>
      <section className="min-w-0 rounded-xl border p-5">{!run ? <div className="py-14 text-center text-muted-foreground"><h2 className="mb-3 text-lg">你的下一次研究，从一个问题开始。</h2><p className="text-sm">研究回答、推荐理由与综述草稿会在这里显示。</p></div> : <><div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">{labels[run.operation] || run.operation}</h2><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!run.report} onClick={download}>下载 Markdown</Button><a className="p-2 text-xs underline" href={`${api.url}/actions/runs/${run.id.split('-')[0]}`} target="_blank" rel="noreferrer">运行详情 ↗</a></div></div><p className="mb-4 text-xs text-muted-foreground">{job?.status === 'completed' && run.status === 'running' ? `运行已结束（${job.conclusion}），结果未持久保存，请查看运行详情。` : run.status} · {run.used_tokens || 0} tokens · {run.elapsed_seconds || 0} 秒</p>
      {run.error && <p role="alert" className="mb-4 text-sm text-destructive">{run.error}</p>}
      {run.trace?.warnings?.map(w => <p key={w} className="mb-3 text-sm">{w}</p>)}
      {['failed', 'partial'].includes(run.status) && ['recommend', 'research', 'review'].includes(run.operation) && <Button className="mb-4" disabled={disabled} onClick={() => submit({ operation: 'retry', target: run.id, budget })}>重试此任务</Button>}
      {run.trace?.recommendations?.map(p => <article key={p.arxiv_id} className="mb-3 rounded-lg border p-4"><a className="font-medium hover:underline" href={`https://arxiv.org/abs/${encodeURIComponent(p.arxiv_id).replace(/%2F/gi, '/')}`} target="_blank" rel="noreferrer">{p.title}</a><p className="my-2 text-sm text-muted-foreground">{p.summary}</p><p className="mb-3 text-xs">兴趣：{p.reasons.matched_interests.join('、') || '无直接匹配'} · 正反馈：{p.reasons.positive_feedback_terms.join('、') || '无'} · 负反馈：{p.reasons.negative_feedback_terms.join('、') || '无'}</p><div className="flex flex-wrap gap-2">{(['like', 'dislike', 'clear'] as const).map(rating => <Button key={rating} size="sm" variant={snapshot?.state.feedback[p.arxiv_id]?.rating === rating ? 'secondary' : 'outline'} disabled={disabled} onClick={() => submit({ operation: 'feedback', paper_ids: p.arxiv_id, feedback: rating })}>{rating === 'like' ? '喜欢' : rating === 'dislike' ? '不喜欢' : '撤销反馈'}</Button>)}</div></article>)}
      <div className="break-words">{run.report ? <MarkdownViewer content={run.report}/> : <p className="text-sm text-muted-foreground">{run.status === 'running' ? '任务正在运行，完成后自动显示结果。' : '此历史任务没有保存网页报告，请查看运行详情与附件。'}</p>}</div>
      {run.report_truncated && <p className="mt-3 text-sm text-muted-foreground">网页报告已截断，完整内容请查看运行附件。</p>}
      {!!run.trace?.sources?.length && <details className="mt-5 text-sm"><summary className="cursor-pointer">本次检索来源（{run.trace.sources.length}）</summary>{run.trace.sources.map(id => <a className="mt-2 block underline" key={id} href={`https://arxiv.org/abs/${encodeURIComponent(id).replace(/%2F/gi, '/')}`} target="_blank" rel="noreferrer">{id}</a>)}</details>}
      {!!run.trace?.calls?.length && <details className="mt-4 text-sm"><summary className="cursor-pointer">工具调用记录</summary>{run.trace.calls.map((call, i) => <p className="mt-2" key={i}>{call.tool} · {call.ok ? '成功' : '失败'}</p>)}</details>}
      {snapshot?.state.drafts[run.id] && <div className="mt-6 space-y-3 border-t pt-4"><h3 className="font-medium">确认保存综述</h3><p className="text-sm text-muted-foreground">请核验来源与结论。确认后创建笔记 PR，供你审查后合并。</p>{confirm === run.id ? <><MarkdownViewer content={snapshot.state.drafts[run.id].content}/><div className="flex gap-2"><Button disabled={disabled} onClick={() => { void submit({ operation: 'approve', target: run.id }); setConfirm('') }}>已核验，创建笔记 PR</Button><Button variant="outline" onClick={() => setConfirm('')}>返回</Button></div></> : <Button variant="outline" onClick={() => setConfirm(run.id)}>审阅完整草稿</Button>}</div>}
      </>}</section></div>
  </div></div>
}
