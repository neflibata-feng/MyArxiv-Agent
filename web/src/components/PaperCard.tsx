import React, { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { AlertCircle, Trash2, ExternalLink, CheckCircle, Copy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Paper } from '@/lib/github'
import { Translation } from '@/i18n/locales'

interface PaperCardProps {
  paper: Paper
  onToggle: () => void
  onDelete: () => void
  t: Translation
}

export function PaperCard({ paper, onToggle, onDelete, t }: PaperCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [copyStatus, setCopyStatus] = useState('')
  const copyLink = async () => {
    try {
      if (!paper.link || !navigator.clipboard) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(paper.link)
      setCopyStatus(t.copiedLink)
    } catch {
      setCopyStatus(t.copyLinkFailed)
    }
  }
  const isUpdate = paper.type === 'update'
  const pdfUrl = (() => {
    try {
      if (!paper.link) return null
      const url = new URL(paper.link)
      if (!['http:', 'https:'].includes(url.protocol) || !['arxiv.org', 'www.arxiv.org'].includes(url.hostname) || !url.pathname.startsWith('/abs/') || url.pathname === '/abs/') return null
      return `https://arxiv.org/pdf/${url.pathname.slice('/abs/'.length)}`
    } catch {
      return null
    }
  })()

  return (
    <Card className={cn(
       "transition-all duration-200 border-l-4 group hover:shadow-md", 
       paper.selected ? "border-l-primary bg-primary/5" : "border-l-transparent",
       isUpdate ? "bg-amber-50/50 dark:bg-amber-950/20" : ""
    )}>
      <CardHeader className="pb-3 pt-4">
        <div className="flex flex-col gap-2">
           <div className="flex justify-between items-start gap-4">
              <div className="space-y-1">
                 <div className="flex items-center gap-2 flex-wrap mb-1">
                    {paper.category && (
                      <Badge variant={isUpdate ? "outline" : "secondary"} className="text-xs font-normal">
                        {paper.category}
                      </Badge>
                    )}
                    {isUpdate && (
                      <Badge variant="destructive" className="flex items-center gap-1 text-xs">
                        <AlertCircle className="h-3 w-3" /> {t.versionUpdate}
                      </Badge>
                    )}
                    <span className="text-xs text-muted-foreground font-mono bg-muted px-1 rounded">{paper.id}</span>
                 </div>
                 <a href={paper.link} target="_blank" className="hover:underline decoration-primary decoration-2 underline-offset-2">
                    <CardTitle className="text-lg leading-tight font-bold text-foreground/90">
                        {paper.title}
                    </CardTitle>
                 </a>
              </div>
              <div className="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                 <Button variant="ghost" size="icon" onClick={onDelete} className="text-muted-foreground hover:text-destructive h-8 w-8">
                   <Trash2 className="h-4 w-4" />
                 </Button>
              </div>
           </div>
           
           {paper.authors && (
             <div className="text-xs text-muted-foreground font-medium">
               {paper.authors} {paper.date && <span>• {paper.date}</span>}
             </div>
           )}
        </div>
      </CardHeader>
      
      <CardContent className="pb-3">
         {isUpdate ? (
           <div className="bg-amber-100/50 dark:bg-amber-900/20 p-3 rounded-md text-sm border border-amber-200 dark:border-amber-800">
              <span className="font-semibold text-amber-800 dark:text-amber-500 block mb-1">{t.updateLog}</span>
              <div className="text-foreground/80 text-xs leading-relaxed">
                 {paper.updateLog || t.noDetails}
              </div>
           </div>
         ) : paper.summary && (
           <div className="relative">
             <div className={cn("text-xs md:text-sm text-muted-foreground leading-relaxed", !expanded && "line-clamp-2")}>
               {paper.summary}
             </div>
             {paper.summary.length > 150 && (
               <Button 
                 variant="link" 
                 size="sm" 
                 className="p-0 h-auto font-normal text-muted-foreground mt-1 text-xs"
                 onClick={() => setExpanded(!expanded)}
               >
                 {expanded ? t.collapse : t.expand}
               </Button>
             )}
           </div>
         )}
      </CardContent>
      
      <CardFooter className="flex justify-between pt-0 gap-3 pb-4">
         <div className="flex gap-2">
            {paper.link && (
               <Button variant="outline" size="sm" className="h-7 text-xs" asChild>
                  <a href={paper.link} target="_blank" rel="noreferrer">
                     <ExternalLink className="h-3 w-3 mr-1" /> Arxiv
                  </a>
               </Button>
            )}
         </div>
         {pdfUrl && <Button variant="outline" size="sm" className="h-7 text-xs" asChild><a href={pdfUrl} target="_blank" rel="noopener noreferrer">{t.openPdf}</a></Button>}
         <div className="flex items-center gap-2">
           <span className="text-xs text-muted-foreground" role="status">{copyStatus}</span>
           {paper.link && <Button variant="ghost" size="sm" onClick={copyLink} aria-label={t.copyLink}><Copy className="h-3 w-3 mr-1" />{t.copyLink}</Button>}
         <Button 
           variant={paper.selected ? "default" : "outline"} 
           size="sm"
           onClick={onToggle}
           className={cn("h-7 text-xs min-w-[80px]", paper.selected && "bg-green-600 hover:bg-green-700")}
         >
           {paper.selected ? (
             <>
                <CheckCircle className="h-3 w-3 mr-2" /> 
                {t.keep}
             </>
           ) : t.collect}
         </Button>
         </div>
      </CardFooter>
    </Card>
  )
}
