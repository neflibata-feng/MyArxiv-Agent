"""GitHub Actions research system: feedback -> learning -> recommendation -> review."""
from __future__ import annotations
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

import yaml
from draft_approval import approve
from learning import feedback, rank
from library_index import build, within
from research_agent import run
from research_sources import get_papers, normalize_id
from review_draft import PROMPT, render
from state_store import StateStore
from subscriptions import collect, apply_progress
from workflow_center import inspect as inspect_workflows, retry_workflow

ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = {'recommend', 'feedback', 'research', 'review', 'approve', 'tasks', 'retry'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def safe(value):
    key = os.environ.get('key', '')
    text = json.dumps(value, ensure_ascii=False)
    if key:
        text = text.replace(json.dumps(key, ensure_ascii=False)[1:-1], '[已隐藏]')
    return json.loads(text)


def md(value):
    return re.sub(r'([\\`*_{}\[\]#|])', r'\\\1', html.escape(str(value))).replace('\n', ' ')


def inputs():
    operation = os.environ.get('RESEARCH_OPERATION', 'recommend')
    if operation not in OPERATIONS:
        raise ValueError('未知研究操作')
    raw_ids = os.environ.get('RESEARCH_PAPER_IDS', '').strip()
    ids = [normalize_id(x) for x in raw_ids.split(',')] if raw_ids else []
    if len(ids) > 10 or any(x is None for x in ids):
        raise ValueError('请填写最多 10 个有效 arXiv ID')
    raw_budget = os.environ.get('RESEARCH_BUDGET') or '1000000'
    if not raw_budget.isascii() or not raw_budget.isdigit() or len(raw_budget) > 7 or not 1 <= int(raw_budget) <= 1_000_000:
        raise ValueError('token 预算须为 1 到 1000000 之间的整数')
    question = os.environ.get('RESEARCH_QUESTION', '').strip()
    if len(question.encode()) > 20000:
        raise ValueError('研究问题超过 20 KB')
    target = os.environ.get('RESEARCH_TARGET', '').strip()
    if len(target) > 100:
        raise ValueError('任务或订阅 ID 过长')
    rating = os.environ.get('RESEARCH_FEEDBACK', 'like')
    ranking = os.environ.get('RESEARCH_RANKING') or 'personalized'
    if rating not in {'like','dislike','clear'} or ranking not in {'personalized','date'}:
        raise ValueError('反馈或排序方式无效')
    if operation == 'feedback' and len(ids) != 1:
        raise ValueError('每次请针对一篇论文提交反馈')
    if operation in {'research','review'} and not question:
        raise ValueError('请填写研究问题')
    if operation in {'approve','retry'} and not target:
        raise ValueError('请填写待确认的草稿或失败任务 ID')
    return {'operation':operation,'ids':ids,'budget':int(raw_budget),'question':question,'target':target,'rating':rating,'ranking':ranking}


def config(root):
    data = yaml.safe_load((root / 'config.yaml').read_text(encoding='utf-8')) or {}
    options = data.get('agent', {})
    if not isinstance(options, dict):
        raise ValueError('agent 配置必须是对象')
    interests = options.get('interests', [])
    if not isinstance(interests,list) or len(interests)>30 or any(not isinstance(x,str) or len(x)>100 for x in interests):
        raise ValueError('agent.interests 须为最多 30 个兴趣短语')
    return data


def local_papers(root, cfg):
    db = within(root, cfg.get('storage',{}).get('sqlite',{}).get('path','data/arxiv.db'))
    if not db.is_file():
        return []
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory=sqlite3.Row
        return [dict(row) for row in conn.execute('''SELECT p.arxiv_id,p.title,p.summary,p.authors,p.link,p.published_at,p.category
          FROM papers p WHERE EXISTS(SELECT 1 FROM inbox_items i WHERE i.arxiv_id=p.arxiv_id AND i.status='pending')
          ORDER BY p.published_at DESC,p.arxiv_id LIMIT 2000''')]


def persist(store, mutate):
    def bounded(current):
        mutate(current)
        # Explicit user feedback is never silently discarded. Evict only rebuildable
        # metadata, old drafts and task history before exceeding the API size limit.
        for field, minimum in [('catalog', 0), ('drafts', 1), ('runs', 5)]:
            while len(json.dumps(current, ensure_ascii=False).encode()) > 800_000 and len(current.get(field, [])) > minimum:
                collection=current[field]
                if isinstance(collection,list):
                    collection.pop(0)
                else:
                    # Keys are serialized in sorted order, so use timestamps for drafts.
                    oldest=min(collection, key=lambda key:collection[key].get('created_at','')) if field=='drafts' else next(iter(collection))
                    collection.pop(oldest)
        sanitized=safe(current)
        current.clear();current.update(sanitized)
    return store.update(bounded)


def remember(state, papers):
    catalog=state.setdefault('catalog',{})
    for paper in papers:
        paper_id=normalize_id(paper.get('arxiv_id'))
        if paper_id:
            catalog.pop(paper_id,None)
            catalog[paper_id] = safe({key:str(paper.get(key) or '')[:3000] for key in ('title','summary','authors','published_at','category')})
    while len(catalog)>200:
        catalog.pop(next(iter(catalog)))


def execute(args, cfg, state, store, root, output, run_id, trace):
    op=args['operation']
    if op=='retry':
        if args['target'].startswith('actions:'):
            result=retry_workflow(store,args['target'])
            trace['retry_of']=args['target']
            return '# 工作流重试\n\n'+md(result['status'])+'：'+result['url']+'\n'
        previous=next((r for r in state['runs'] if r['id']==args['target']),None)
        if not previous or previous['status'] not in {'failed','partial'} or previous['operation'] not in {'research','review','recommend'}:
            raise ValueError('仅可重试失败的研究、综述或推荐任务')
        restored=previous.get('inputs')
        if not isinstance(restored,dict) or restored.get('operation')!=previous['operation']:
            raise ValueError('历史任务参数与操作不一致，拒绝重放')
        ids=restored.get('ids')
        question=restored.get('question')
        target=restored.get('target')
        if not isinstance(ids,list) or len(ids)>10 or any(normalize_id(x)!=x or x is None for x in ids):
            raise ValueError('历史论文 ID 无效')
        if not isinstance(question,str) or len(question.encode())>20000 or not isinstance(target,str) or len(target)>100:
            raise ValueError('历史任务参数无效')
        if previous['operation'] in {'research','review'} and not question.strip():
            raise ValueError('历史研究问题缺失')
        if restored.get('ranking') not in {'personalized','date'} or restored.get('rating') not in {'like','dislike','clear'}:
            raise ValueError('历史任务选项无效')
        args={**restored,'operation':previous['operation'],'budget':args['budget']}
        trace['retry_of']=previous['id']
        trace['effective_inputs']=safe(args)
        return execute(args,cfg,state,store,root,output,run_id,trace)
    if op=='feedback':
        paper_id=args['ids'][0]
        paper=state.get('catalog',{}).get(paper_id)
        if not paper and args['rating']!='clear':
            db=within(root,cfg.get('storage',{}).get('sqlite',{}).get('path','data/arxiv.db'))
            found=get_papers(db,[paper_id])
            paper=found[0] if found else None
        if not paper and args['rating']!='clear':
            raise ValueError('未找到论文；请先推荐或将论文加入仓库')
        text=(paper or {}).get('title','')+' '+(paper or {}).get('summary','')
        persist(store, lambda current: feedback(current,paper_id,args['rating'],text))
        return '# 反馈已保存\n\n'+md(paper_id)+'：'+args['rating']+'。后续推荐会使用更新后的反馈。\n'
    if op=='approve':
        result=approve(store,args['target'],cfg)
        return '# 综述已提交待审查\n\nPR：'+result['url']+'\n'
    if op=='tasks':
        lines=['# 任务运行中心','','兴趣：'+md(', '.join(cfg.get('agent',{}).get('interests',[])))+'；显式论文反馈 '+str(len(state['feedback']))+' 条','','## 研究系统任务','']
        for record in reversed(state['runs'][-30:]):
            lines.append('- '+md(record['id'])+' · '+md(record['operation'])+' · '+md(record['status'])+' · '+str(record.get('elapsed_seconds',0))+' 秒 · '+str(record.get('used_tokens',0))+' tokens'+(' · '+md(record.get('error','')) if record.get('error') else ''))
        lines+=['',inspect_workflows(store),'','失败研究任务可选择 retry 并填写任务 ID；抓取或归档任务填写 actions:运行编号。反馈和确认操作禁止重放。']
        return '\n'.join(lines)+'\n'
    if op=='recommend':
        papers,progress,report=collect(cfg,state,args['target'])
        unique={normalize_id(p['arxiv_id']):p for p in [*local_papers(root,cfg),*papers] if normalize_id(p.get('arxiv_id'))}
        ranked=rank(list(unique.values()),cfg.get('agent',{}).get('interests',[]),state,args['ranking']=='personalized')
        result={'ranking':args['ranking'],'papers':ranked,'subscriptions':report}
        (output/'recommendations.json').write_text(json.dumps(safe(result),ensure_ascii=False,indent=2),encoding='utf-8')
        lines=['# 论文推荐','','排序：'+args['ranking']+'；根据显式兴趣与反馈调整，不修改模型参数。','']
        for p in ranked[:30]:
            lines+=['## '+md(p['title']),'https://arxiv.org/abs/'+normalize_id(p['arxiv_id']),md(p.get('summary','')[:600]),'','推荐依据：'+md(json.dumps(p['reasons'],ensure_ascii=False))+'；得分 '+str(p['score']),'']
        if not ranked:
            lines.append('本次没有待处理论文或新订阅结果。请初始化数据库，或在 config.yaml 配置 agent.subscriptions。')
        for topic_id,row in report.get('topics',{}).items():
            lines.append('订阅 '+md(topic_id)+'：'+md(json.dumps(row,ensure_ascii=False)))
        # Save progress only after successful ranking/output. Merge on the latest state.
        def save(current):
            apply_progress(current,progress)
            remember(current,[*papers,*ranked[:100]])
        persist(store, save)
        if report.get('failed'):
            trace['warnings']=['部分订阅失败，成功订阅的进度已保存，可按订阅 ID 重跑']
        return '\n'.join(lines)+'\n'
    index=output.parent/'library.sqlite'
    trace['index']=build(root,cfg,index)
    os.environ['RESEARCH_INDEX']=str(index)
    if op=='review':
        raw,used=run(PROMPT+'\n研究问题：'+args['question'],budget=args['budget'],root=root,selected_ids=args['ids'],trace=trace,structured=True)
        answer=safe(render(raw,trace.get('sources',[])))
        if not trace.get('sources'):
            raise ValueError('本次未检索到论文来源，不保存综述草稿')
        digest=hashlib.sha256(answer.encode()).hexdigest()
        draft={'content':answer,'sha256':digest,'created_at':now()}
        def save_draft(current):
            drafts=current.setdefault('drafts',{})
            drafts[run_id]=draft
            while len(drafts)>20:
                drafts.pop(min(drafts,key=lambda key:drafts[key].get('created_at','')))
        persist(store, save_draft)
        answer+='\n\n草稿 ID：`'+run_id+'`。检查后，手动运行 approve 并填写此 ID，才会将笔记提交为正式 PR。\n'
    else:
        answer,used=run(args['question'],budget=args['budget'],root=root,selected_ids=args['ids'],trace=trace)
    trace['used_tokens']=used
    return answer


def main():
    started=time.monotonic(); args=None; trace={}; store=None
    run_id=os.environ.get('GITHUB_RUN_ID','0')+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','1')
    output=Path(os.environ.get('RESEARCH_OUTPUT',os.environ.get('RUNNER_TEMP','/tmp')+'/research-results'))
    output.mkdir(parents=True,exist_ok=True)
    record={'id':run_id,'started_at':now(),'status':'running','operation':'invalid'}
    code=0
    try:
        args=inputs();record.update(operation=args['operation'],inputs=safe(args))
        cfg=config(ROOT);store=StateStore()
        state,_=store.load()
        def start(current):
            current['runs']=[r for r in current['runs'] if r['id']!=run_id][-99:]+[record]
        persist(store, start)
        answer=execute(args,cfg,state,store,ROOT,output,run_id,trace)
        record['status']='partial' if trace.get('warnings') else 'completed'
    except Exception as exc:
        # Never expose provider response bodies or credential-bearing request objects.
        code=1;record['status']='failed'
        message=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__+'：请检查配置及运行日志'
        record['error']=safe(message)[:500]
        answer='# 研究任务失败\n\n'+md(record['error'])+'\n'
    effective=trace.pop('effective_inputs',None)
    if effective is not None:
        record.update(requested_operation='retry',operation=effective['operation'],inputs=effective)
    record.update(ended_at=now(),elapsed_seconds=round(time.monotonic()-started,2),used_tokens=trace.get('used_tokens',0),trace=safe(trace))
    record=safe(record);answer=safe(answer)
    try:
        if store:
            def finish(current):
                current['runs']=[r for r in current['runs'] if r['id']!=run_id][-99:]+[record]
            persist(store, finish)
    except Exception:
        code=1;answer+='\n任务记录未能持久保存；现有研究状态未被覆盖，请查看本次附件。\n'
    (output/'report.md').write_text(answer,encoding='utf-8')
    (output/'run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a',encoding='utf-8') as out:
            out.write(answer[:200000]+'\n\n任务 ID：'+run_id+'\n')
    print('研究任务状态：'+record['status']+'；详情见 Summary 和附件')
    return code


if __name__=='__main__':
    raise SystemExit(main())
