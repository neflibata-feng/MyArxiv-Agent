import React, { useState, useEffect, useRef } from 'react'
import { GithubClient, RepoFile } from '@/lib/github'
import { Translation } from '@/i18n/locales'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { FileText, Save, SplitSquareHorizontal, Minimize } from 'lucide-react'
import { MarkdownViewer } from '@/components/MarkdownViewer'
import { cn } from '@/lib/utils'
import { RepoFileTree } from '@/components/RepoFileTree'

interface WorkbenchViewProps {
  client: GithubClient
  t: Translation
  searchTerm: string
   config: any
}

export function WorkbenchView({ client, t, searchTerm, config }: WorkbenchViewProps) {
  const [showFiles, setShowFiles] = useState(false)
  const [activeFile, setActiveFile] = useState<RepoFile | null>(null)
  const [content, setContent] = useState("")
  const [viewMode, setViewMode] = useState<'split' | 'single'>('single')
  const [isEditing, setIsEditing] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef(0)

   const rootPath = config?.paths?.notes_dir || 'Notes'

   useEffect(() => {
      requestId.current += 1
      setLoading(false)
      setError('')
      setActiveFile(null)
      setContent('')
      setDirty(false)
      setIsEditing(false)
   }, [rootPath])

  const loadFile = async (file: RepoFile) => {
    if (saving || (dirty && !window.confirm(t.discardUnsaved))) return
    const id = ++requestId.current
    setLoading(true)
    setError('')
    try {
      const result = await client.getFileContent(file.path)
      if (id !== requestId.current) return
      setActiveFile({ ...file, sha: result.sha })
      setContent(result.content)
      setDirty(false)
      setIsEditing(false)
    } catch {
      if (id === requestId.current) setError(t.loadFileFailed)
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  const saveFile = async () => {
    if (!activeFile || loading || saving) return
    const id = requestId.current
    setSaving(true)
    setError('')
    try {
      await client.updateFile(activeFile.path, content, activeFile.sha, `Update Note ${activeFile.name}`)
      const { sha } = await client.getFileContent(activeFile.path, true)
      if (id !== requestId.current) return
      setActiveFile({ ...activeFile, sha })
      setDirty(false)
    } catch {
      if (id === requestId.current) setError(t.saveFail)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full relative">
       <Button className="md:hidden absolute bottom-3 right-3 z-10" variant="outline" onClick={() => setShowFiles(true)} aria-expanded={showFiles}>{t.openNotes}</Button>
       <div className={cn("w-64 border-r bg-card overflow-y-auto flex-col md:flex", showFiles ? "absolute inset-y-0 left-0 z-20 max-w-[80%] flex md:static md:z-auto md:max-w-none" : "hidden")}>
          <div className="p-4 font-semibold border-b bg-muted/20 flex items-center justify-between">{t.workbench}<Button className="md:hidden" variant="ghost" size="sm" onClick={() => setShowFiles(false)}>{t.closeNotes}</Button></div>
               <div className="flex-1 p-2">
                  <RepoFileTree
                     client={client}
                     rootPath={rootPath}
                     selectedPath={activeFile?.path}
                     onSelectFile={file => { setShowFiles(false); loadFile(file) }}
                     searchTerm={searchTerm}
                     fileFilter={(f) => f.type === 'file' && f.name.toLowerCase().endsWith('.md')}
                     loadingLabel={t.loading}
                     errorLabel={t.directoryLoadFailed}
                     retryLabel={t.retry}
                  />
               </div>
       </div>
       
       <div className="flex-1 flex flex-col h-full bg-background overflow-hidden">
          {error && <div role="alert" className="p-3 text-sm text-destructive">{error}</div>}
          {loading && <div role="status" className="p-3 text-sm">{t.loading}</div>}
          {activeFile ? (
             <>
               <div className="h-12 border-b flex items-center justify-between px-4 sticky top-0 bg-background/95 backdrop-blur z-10">
                  <div className="flex items-center gap-2">
                     <span className="font-semibold text-sm">{activeFile.name}</span>
                     {dirty && <Badge variant="outline" className="text-yellow-600 border-yellow-600 h-5">Modified</Badge>}
                  </div>
                  <div className="flex gap-2">
                     <Button variant="ghost" size="sm" onClick={() => setViewMode(v => v === 'split' ? 'single' : 'split')}>
                        {viewMode === 'split' ? <Minimize className="h-4 w-4 mr-2"/> : <SplitSquareHorizontal className="h-4 w-4 mr-2"/>}
                        {viewMode === 'split' ? t.singleView : t.splitView}
                     </Button>
                     <Button size="sm" disabled={!dirty || loading || saving} onClick={saveFile}>
                        <Save className="h-4 w-4 mr-2"/> {t.save}
                     </Button>
                  </div>
               </div>
               
               <div className="flex-1 flex overflow-hidden">
                   {/* Editor Pane */}
                   <div className={cn("flex-1 flex flex-col border-r h-full", viewMode === 'single' && !isEditing ? "hidden" : "block")}>
                      <textarea 
                        className="flex-1 w-full h-full p-6 resize-none focus:outline-none font-mono text-sm bg-background text-foreground leading-relaxed"
                        disabled={loading || saving}
                        onKeyDown={event => {
                          if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && !event.nativeEvent.isComposing) {
                            event.preventDefault()
                            if (dirty && !loading && !saving) saveFile()
                          }
                        }}
                        value={content}
                        onChange={e => { setContent(e.target.value); setDirty(true); setIsEditing(true) }}
                                    placeholder={t.writeMarkdownHere}
                      />
                   </div>
                   
                   {/* Preview Pane */}
                   <div className={cn("flex-1 h-full overflow-y-auto p-8 bg-card", viewMode === 'single' && isEditing ? "hidden" : "block")}>
                       <MarkdownViewer
                         content={content || "*Empty file*"}
                         resolveAssetUrl={(url) => client.resolveRawUrl(url, activeFile.path)}
                       />
                   </div>
               </div>
             </>
          ) : (
             <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <FileText className="h-16 w-16 mb-4 opacity-20" />
                <p>{t.selectFileToEdit}</p>
             </div>
          )}
       </div>
    </div>
  )
}
