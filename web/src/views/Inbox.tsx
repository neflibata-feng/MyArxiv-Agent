import { useState, useEffect, useMemo } from 'react'
import { GithubClient, Paper } from '@/lib/github'
import { Translation } from '@/i18n/locales'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Calendar, RefreshCw, Save } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PaperCard } from '@/components/PaperCard'
import Fuse from 'fuse.js'

interface InboxViewProps {
  client: GithubClient
  t: Translation
  searchTerm: string
}

export function InboxView({ client, t, searchTerm }: InboxViewProps) {
  const [papers, setPapers] = useState<Paper[]>([])
  const [initialPapers, setInitialPapers] = useState<Paper[]>([])
  const [originalContent, setOriginalContent] = useState<string>("")
  const [sha, setSha] = useState<string>("")
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [activeGroup, setActiveGroup] = useState<string | null>(null)

  const fetchInbox = async () => {
    setLoading(true)
    try {
      const { content, sha } = await client.getFileContent("Inbox.md")
      const parsed = GithubClient.parseInbox(content)
      setOriginalContent(content)
      setSha(sha)
      setPapers(parsed)
      setInitialPapers(parsed)
      if (parsed.length > 0 && !activeGroup) setActiveGroup(parsed[0].group || null)
    } catch(e) { console.error(e) } 
    finally { setLoading(false) }
  }

  useEffect(() => { fetchInbox() }, [])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const newContent = GithubClient.reconstructInbox(originalContent, papers)
      await client.updateFile("Inbox.md", newContent, sha, `MyArxiv-Agent Sync ${new Date().toISOString()}`)
      await fetchInbox()
    } catch(e) { console.error(e) } 
    finally { setSyncing(false) }
  }

  const changesCount = useMemo(() => {
     if (initialPapers.length === 0) return 0
     const initialMap = new Map(initialPapers.map(p => [p.id, p]))
     const currentIds = new Set(papers.map(p => p.id))
     const deleted = initialPapers.filter(p => !currentIds.has(p.id)).length
     const modified = papers.filter(p => {
       const init = initialMap.get(p.id)
       return init && init.selected !== p.selected
     }).length
     return deleted + modified
  }, [papers, initialPapers])
  
  // Filter by Search
  const filteredPapers = useMemo(() => {
    if (!searchTerm) return papers
    const fuse = new Fuse(papers, {
      includeScore: true,
      threshold: 0.35,
      ignoreLocation: true,
      minMatchCharLength: 2,
      keys: [
        { name: 'title', weight: 0.5 },
        { name: 'id', weight: 0.4 },
        { name: 'summary', weight: 0.3 },
        { name: 'authors', weight: 0.2 },
        { name: 'category', weight: 0.2 },
        { name: 'group', weight: 0.2 },
      ],
    })

    return fuse.search(searchTerm).map(r => r.item)
  }, [papers, searchTerm])

  const groups = useMemo(() => {
    const map = new Map<string, Paper[]>()
    const order: string[] = []
    filteredPapers.forEach(p => {
       const g = p.group || "Other"
       if (!map.has(g)) { map.set(g, []); order.push(g) }
       map.get(g)?.push(p)
    })
    return order.map(g => ({ name: g, papers: map.get(g)||[] }))
  }, [filteredPapers])
  
  const displayed = useMemo(() => activeGroup ? filteredPapers.filter(p => (p.group||"Other") === activeGroup) : filteredPapers, [filteredPapers, activeGroup])

  return (
    <div className="flex h-full">
       <aside className="w-64 border-r overflow-y-auto hidden md:block bg-muted/10 p-4">
          <h2 className="font-semibold mb-2 px-2 flex items-center gap-2"><Calendar className="h-4 w-4"/> {t.timeline}</h2>
          <div className="space-y-1">
            {groups.map(g => (
               <Button key={g.name} variant={activeGroup===g.name?"secondary":"ghost"} className="w-full justify-start h-auto py-2 text-left" onClick={()=>setActiveGroup(g.name)}>
                 <div className="w-full truncate">
                    <div className="font-medium truncate">{g.name.replace(/^##\s*/,'')}</div>
                    <div className="text-xs text-muted-foreground">{g.papers.length} {t.items}</div>
                 </div>
               </Button>
            ))}
          </div>
       </aside>
       <div className="flex-1 flex flex-col h-full overflow-hidden">
          <div className="p-4 border-b flex items-center justify-between bg-muted/10">
             <span className="text-sm font-medium flex items-center gap-2">
                <Calendar className="h-4 w-4" /> {t.inbox}
                {searchTerm && <Badge variant="secondary">{t.found} {filteredPapers.length}</Badge>}
             </span>
             <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={fetchInbox} disabled={loading}>
                   <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} /> {t.refresh}
                </Button>
                <Button size="sm" onClick={handleSync} disabled={syncing}>
                   <Save className="h-4 w-4 mr-2"/> {t.sync} ({changesCount})
                </Button>
             </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
             {displayed.map(p => (
               <PaperCard key={p.id} paper={p} t={t} 
                 onToggle={() => setPapers(prev => prev.map(x => x.id===p.id ? {...x, selected: !x.selected} : x))}
                 onDelete={() => setPapers(prev => prev.filter(x => x.id!==p.id))}
               />
             ))}
             {displayed.length === 0 && <div className="text-center text-muted-foreground mt-10">{t.noPapers}</div>}
          </div>
       </div>
    </div>
  )
}
