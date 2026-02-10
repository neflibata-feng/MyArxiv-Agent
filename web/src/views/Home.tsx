import React, { useState, useEffect } from 'react'
import { GithubClient } from '@/lib/github'
import { MarkdownViewer } from '@/components/MarkdownViewer'

interface HomeViewProps {
  client: GithubClient
  config: any
}

export function HomeView({ client, config }: HomeViewProps) {
  const [content, setContent] = useState("")
  const homePath = config?.ui?.home_path || config?.home_path || "README.md" 

  useEffect(() => {
    client.getFileContent(homePath).then(res => {
         setContent(res.content)
    }).catch(console.error)
  }, [client, homePath])

  return (
    <div className="h-full overflow-y-auto p-6 md:p-10">
       <div className="max-w-4xl mx-auto bg-card rounded-xl p-8 shadow-sm border">
          <MarkdownViewer content={content} />
       </div>
    </div>
  )
}
