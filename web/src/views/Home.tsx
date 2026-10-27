import React, { useState, useEffect } from 'react'
import { GithubClient } from '@/lib/github'
import { MarkdownViewer } from '@/components/MarkdownViewer'
import { Translation } from '@/i18n/locales'

interface HomeViewProps {
  client: GithubClient
  config: any
  t: Translation
}

export function HomeView({ client, config, t }: HomeViewProps) {
  const [content, setContent] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const homePath = config?.ui?.home_path || config?.home_path || "README.md" 

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(false)
    setContent('')
    client.getFileContent(homePath).then(res => {
      if (active) setContent(res.content)
    }).catch(() => {
      if (active) setError(true)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [client, homePath])

  return (
    <div className="h-full overflow-y-auto p-6 md:p-10">
       <div className="max-w-4xl mx-auto bg-card rounded-xl p-8 shadow-sm border">
          {loading ? <div role="status">{t.loading}</div> : error ? <div role="alert">{t.homeLoadFailed}</div> : (
            <MarkdownViewer
              content={content}
              resolveAssetUrl={(url) => client.resolveRawUrl(url, homePath)}
            />
          )}
       </div>
    </div>
  )
}
