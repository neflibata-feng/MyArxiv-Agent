import React, { useState, useEffect } from 'react'
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
  const [activeFile, setActiveFile] = useState<RepoFile | null>(null)
  const [content, setContent] = useState("")
  const [viewMode, setViewMode] = useState<'split' | 'single'>('single')
  const [isEditing, setIsEditing] = useState(false)
  const [dirty, setDirty] = useState(false)

   const rootPath = config?.paths?.notes_dir || 'Notes'

   useEffect(() => {
      setActiveFile(null)
      setContent('')
      setDirty(false)
      setIsEditing(false)
   }, [rootPath])

  const loadFile = async (file: RepoFile) => {
    setActiveFile(file)
    setDirty(false)
    setIsEditing(false)
    const { content } = await client.getFileContent(file.path)
    setContent(content)
  }

  const saveFile = async () => {
    if (!activeFile) return
    await client.updateFile(activeFile.path, content, activeFile.sha, `Update Note ${activeFile.name}`)
    const { sha } = await client.getFileContent(activeFile.path, true) // Force refresh
    setActiveFile({ ...activeFile, sha })
    setDirty(false)
  }

  return (
    <div className="flex h-full">
       <div className="w-64 border-r bg-muted/10 overflow-y-auto flex flex-col">
          <div className="p-4 font-semibold border-b bg-muted/20">{t.workbench}</div>
               <div className="flex-1 p-2">
                  <RepoFileTree
                     client={client}
                     rootPath={rootPath}
                     selectedPath={activeFile?.path}
                     onSelectFile={loadFile}
                     searchTerm={searchTerm}
                     fileFilter={(f) => f.type === 'file' && f.name.toLowerCase().endsWith('.md')}
                     loadingLabel={t.loading}
                  />
               </div>
       </div>
       
       <div className="flex-1 flex flex-col h-full bg-background overflow-hidden">
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
                     <Button size="sm" disabled={!dirty} onClick={saveFile}>
                        <Save className="h-4 w-4 mr-2"/> {t.save}
                     </Button>
                  </div>
               </div>
               
               <div className="flex-1 flex overflow-hidden">
                   {/* Editor Pane */}
                   <div className={cn("flex-1 flex flex-col border-r h-full", viewMode === 'single' && !isEditing ? "hidden" : "block")}>
                      <textarea 
                        className="flex-1 w-full h-full p-6 resize-none focus:outline-none font-mono text-sm bg-background text-foreground leading-relaxed"
                        value={content}
                        onChange={e => { setContent(e.target.value); setDirty(true); setIsEditing(true) }}
                                    placeholder={t.writeMarkdownHere}
                      />
                   </div>
                   
                   {/* Preview Pane */}
                   <div className={cn("flex-1 h-full overflow-y-auto p-8 bg-card", viewMode === 'single' && isEditing ? "hidden" : "block")}>
                       <MarkdownViewer content={content || "*Empty file*"} />
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
