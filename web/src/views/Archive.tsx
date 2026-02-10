import { useEffect, useMemo, useState } from 'react'
import { GithubClient, RepoFile } from '@/lib/github'
import { Translation } from '@/i18n/locales'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText, ExternalLink } from 'lucide-react'
import { RepoFileTree } from '@/components/RepoFileTree'
import { MarkdownViewer } from '@/components/MarkdownViewer'

interface ArchiveViewProps {
  client: GithubClient
  t: Translation
  searchTerm: string
   config: any
}

export function ArchiveView({ client, t, searchTerm, config }: ArchiveViewProps) {
   const rootPath = useMemo(() => config?.paths?.papers_dir || 'Papers', [config])
   const [activeFile, setActiveFile] = useState<RepoFile | null>(null)
   const [content, setContent] = useState<string>('')
   const [loading, setLoading] = useState(false)

   const isMarkdown = (path?: string | null) => !!path && path.toLowerCase().endsWith('.md')

   useEffect(() => {
      setActiveFile(null)
      setContent('')
   }, [rootPath])

   const loadFile = async (file: RepoFile) => {
      setActiveFile(file)
      if (!isMarkdown(file.path)) {
         setContent('')
         return
      }
      setLoading(true)
      try {
         const res = await client.getFileContent(file.path)
         setContent(res.content)
      } finally {
         setLoading(false)
      }
   }

  return (
     <div className="flex h-full">
            <aside className="w-72 border-r bg-muted/10 overflow-y-auto hidden md:block">
               <div className="p-4 font-semibold border-b bg-muted/20">{t.archive}</div>
               <div className="p-2">
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
            </aside>

            <div className="flex-1 overflow-hidden">
               <div className="h-full overflow-y-auto p-6">
                  {!activeFile && (
                     <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                        <FileText className="h-16 w-16 mb-4 opacity-20" />
                        <p>{t.selectMarkdownFile}</p>
                     </div>
                  )}

                  {activeFile && (
                     <Card>
                        <CardHeader className="pb-3">
                           <CardTitle className="text-base flex items-center gap-2">
                              <FileText className="h-4 w-4 text-muted-foreground" />
                              <span className="truncate">{activeFile.path}</span>
                           </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-0">
                           {!isMarkdown(activeFile.path) && (
                              <div className="text-sm text-muted-foreground flex items-center gap-2">
                                 <span>{t.mdOnlyPreview}</span>
                                 {activeFile.download_url && (
                                    <a
                                       href={activeFile.download_url}
                                       target="_blank"
                                       rel="noreferrer"
                                       className="text-primary hover:underline inline-flex items-center gap-1"
                                    >
                                       <ExternalLink className="h-4 w-4" /> {t.open}
                                    </a>
                                 )}
                              </div>
                           )}

                           {isMarkdown(activeFile.path) && (
                              <MarkdownViewer content={loading ? t.loading : content || t.emptyFile} />
                           )}
                        </CardContent>
                     </Card>
                  )}
               </div>
            </div>
     </div>
  )
}
