import React, { useState, useEffect } from 'react'
import { GithubClient } from '@/lib/github'
import { Translation } from '@/i18n/locales'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Save, RefreshCw } from 'lucide-react'
import yaml from 'js-yaml'

interface SettingsViewProps {
  client: GithubClient
  t: Translation
  appConfig: any
  globalConfig: any
  setGlobalConfig: (c: any) => void
}

export function SettingsView({ client, t, appConfig, globalConfig, setGlobalConfig }: SettingsViewProps) {
   const [rawContent, setRawContent] = useState("")
   const [sha, setSha] = useState("")
   const [loading, setLoading] = useState(false)
   const [yamlError, setYamlError] = useState<string>("")

   // Load config
   useEffect(() => {
     client.getFileContent("config.yaml").then((res: any) => {
        setRawContent(res.content)
        setSha(res.sha)
        try {
           const parsed = yaml.load(res.content)
           if (typeof parsed === 'object') setGlobalConfig(parsed)
           setYamlError("")
        } catch (e) { console.error("YAML Parse Error", e) }
     })
   }, [])

   const handleSave = async () => {
     setLoading(true)
     try {
       await client.updateFile("config.yaml", rawContent, sha, "Update config")
       // Update hash and local state
       const res = await client.getFileContent("config.yaml", true)
       setSha(res.sha)
       alert(t.saveSuccess)
     } catch(e) { 
        console.error(e)
        alert(t.saveFail)
     } finally { setLoading(false) }
   }

   const setNestedValue = (obj: any, path: string[], value: any) => {
      let cur = obj
      for (let i = 0; i < path.length - 1; i++) {
         const key = path[i]
         const next = cur[key]
         if (!next || typeof next !== 'object') cur[key] = {}
         cur = cur[key]
      }
      cur[path[path.length - 1]] = value
   }

   const getNestedValue = (obj: any, path: string[], fallback: any = "") => {
      let cur = obj
      for (const key of path) {
         if (!cur || typeof cur !== 'object' || !(key in cur)) return fallback
         cur = cur[key]
      }
      return cur ?? fallback
   }

   const updatePath = (path: string[], value: any) => {
      const next = JSON.parse(JSON.stringify(globalConfig || {}))
      setNestedValue(next, path, value)
      setGlobalConfig(next)
      try {
         setRawContent(yaml.dump(next, { lineWidth: 120 }))
         setYamlError("")
      } catch {}
   }

   const parseLines = (text: string) =>
      text
        .split(/\r?\n/)
        .map(s => s.trim())
        .filter(Boolean)

   return (
     <div className="max-w-4xl mx-auto p-6 space-y-8 h-full overflow-y-auto">
        <div>
           <h2 className="text-2xl font-bold mb-2">{t.settings}</h2>
           <p className="text-muted-foreground mb-6">{t.configDesc}</p>
           
           <Card className="mb-6">
              <CardHeader>
                 <CardTitle className="text-base">{t.theme} & {t.lang}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-4">
                 <div className="flex gap-2">
                    {['light', 'dark', 'system'].map((m: any) => (
                       <Button key={m} variant={appConfig.theme === m ? "default" : "outline"} onClick={() => appConfig.setTheme(m)}>
                          {m.charAt(0).toUpperCase() + m.slice(1)}
                       </Button>
                    ))}
                 </div>
                 <div className="w-px bg-border h-9 mx-2"/>
                 <div className="flex gap-2">
                    <Button variant={appConfig.lang === 'zh' ? "default" : "outline"} onClick={() => appConfig.setLang('zh')}>中文</Button>
                    <Button variant={appConfig.lang === 'en' ? "default" : "outline"} onClick={() => appConfig.setLang('en')}>English</Button>
                 </div>
              </CardContent>
           </Card>

           <Card>
                <CardHeader>
                    <CardTitle className="text-base">{t.config}</CardTitle>
                </CardHeader>
                        <CardContent className="p-6 space-y-8">
                           {/* UI */}
                           <div className="space-y-3">
                              <div className="font-medium text-sm">{t.uiSection}</div>
                              <div className="grid w-full max-w-md items-center gap-1.5">
                                 <label htmlFor="ui-home-path" className="text-sm font-medium">{t.homeMarkdownPathLabel}</label>
                                 <input
                                    id="ui-home-path"
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                    value={getNestedValue(globalConfig, ['ui', 'home_path'], '')}
                                    onChange={e => updatePath(['ui', 'home_path'], e.target.value)}
                                    placeholder="README.md"
                                 />
                                 <p className="text-xs text-muted-foreground">{t.homeMarkdownPathHint}</p>
                              </div>
                           </div>

                           {/* Paths */}
                           <div className="space-y-3">
                              <div className="font-medium text-sm">{t.pathsSection}</div>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                 {(
                                    [
                                       { key: 'inbox', label: 'Inbox', placeholder: 'Inbox.md' },
                                       { key: 'contents', label: 'Contents', placeholder: 'Contents.md' },
                                       { key: 'papers_dir', label: 'Papers Dir', placeholder: 'Papers' },
                                       { key: 'notes_dir', label: 'Notes Dir', placeholder: 'Notes' },
                                       { key: 'pdfs_dir', label: 'PDFs Dir', placeholder: 'pdfs' },
                                    ] as const
                                 ).map(item => (
                                    <div key={item.key} className="grid items-center gap-1.5">
                                       <label htmlFor={`path-${item.key}`} className="text-sm font-medium">{item.label}</label>
                                       <input
                                          id={`path-${item.key}`}
                                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                          value={getNestedValue(globalConfig, ['paths', item.key], '')}
                                          onChange={e => updatePath(['paths', item.key], e.target.value)}
                                          placeholder={item.placeholder}
                                       />
                                    </div>
                                 ))}
                              </div>
                           </div>

                           {/* Fetch / API */}
                           <div className="space-y-3">
                              <div className="font-medium text-sm">{t.fetchSection}</div>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="fetch-sort-by" className="text-sm font-medium">sort_by</label>
                                    <input
                                       id="fetch-sort-by"
                                       className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={getNestedValue(globalConfig, ['fetch', 'arxiv_api', 'sort_by'], '')}
                                       onChange={e => updatePath(['fetch', 'arxiv_api', 'sort_by'], e.target.value)}
                                       placeholder="submittedDate"
                                    />
                                 </div>
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="fetch-sort-order" className="text-sm font-medium">sort_order</label>
                                    <input
                                       id="fetch-sort-order"
                                       className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={getNestedValue(globalConfig, ['fetch', 'arxiv_api', 'sort_order'], '')}
                                       onChange={e => updatePath(['fetch', 'arxiv_api', 'sort_order'], e.target.value)}
                                       placeholder="descending"
                                    />
                                 </div>
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="fetch-start" className="text-sm font-medium">start</label>
                                    <input
                                       id="fetch-start"
                                       type="number"
                                       className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={String(getNestedValue(globalConfig, ['fetch', 'arxiv_api', 'start'], 0))}
                                       onChange={e => updatePath(['fetch', 'arxiv_api', 'start'], Number(e.target.value))}
                                       placeholder="0"
                                    />
                                 </div>
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="fetch-max-results" className="text-sm font-medium">max_results</label>
                                    <input
                                       id="fetch-max-results"
                                       type="number"
                                       className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={String(getNestedValue(globalConfig, ['fetch', 'arxiv_api', 'max_results'], 150))}
                                       onChange={e => updatePath(['fetch', 'arxiv_api', 'max_results'], Number(e.target.value))}
                                       placeholder="150"
                                    />
                                 </div>
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="fetch-timeout" className="text-sm font-medium">timeout_seconds</label>
                                    <input
                                       id="fetch-timeout"
                                       type="number"
                                       className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={String(getNestedValue(globalConfig, ['fetch', 'arxiv_api', 'http', 'timeout_seconds'], 30))}
                                       onChange={e => updatePath(['fetch', 'arxiv_api', 'http', 'timeout_seconds'], Number(e.target.value))}
                                       placeholder="30"
                                    />
                                 </div>
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="fetch-retries" className="text-sm font-medium">retries</label>
                                    <input
                                       id="fetch-retries"
                                       type="number"
                                       className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={String(getNestedValue(globalConfig, ['fetch', 'arxiv_api', 'http', 'retries'], 3))}
                                       onChange={e => updatePath(['fetch', 'arxiv_api', 'http', 'retries'], Number(e.target.value))}
                                       placeholder="3"
                                    />
                                 </div>
                              </div>
                           </div>

                           {/* Fetch / Query */}
                           <div className="space-y-3">
                              <div className="font-medium text-sm">{t.querySection}</div>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="query-categories" className="text-sm font-medium">{t.categoriesOnePerLine}</label>
                                    <textarea
                                       id="query-categories"
                                       className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={(getNestedValue(globalConfig, ['fetch', 'query', 'categories'], []) as any[]).join('\n')}
                                       onChange={e => updatePath(['fetch', 'query', 'categories'], parseLines(e.target.value))}
                                       placeholder={'cs.AI\ncs.CL'}
                                    />
                                 </div>
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="query-keywords" className="text-sm font-medium">{t.keywordsOnePerLine}</label>
                                    <textarea
                                       id="query-keywords"
                                       className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={(getNestedValue(globalConfig, ['fetch', 'query', 'keywords'], []) as any[]).join('\n')}
                                       onChange={e => updatePath(['fetch', 'query', 'keywords'], parseLines(e.target.value))}
                                       placeholder={'Agent\nRAG'}
                                    />
                                 </div>
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="query-keyword-field" className="text-sm font-medium">keyword_field</label>
                                    <input
                                       id="query-keyword-field"
                                       className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={getNestedValue(globalConfig, ['fetch', 'query', 'keyword_field'], '')}
                                       onChange={e => updatePath(['fetch', 'query', 'keyword_field'], e.target.value)}
                                       placeholder="all"
                                    />
                                 </div>
                                 <div className="grid items-center gap-1.5">
                                    <label htmlFor="query-combine-mode" className="text-sm font-medium">combine_mode</label>
                                    <input
                                       id="query-combine-mode"
                                       className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                       value={getNestedValue(globalConfig, ['fetch', 'query', 'combine_mode'], '')}
                                       onChange={e => updatePath(['fetch', 'query', 'combine_mode'], e.target.value)}
                                       placeholder="(cat_or) AND (kw_or)"
                                    />
                                 </div>
                              </div>
                           </div>

                           {/* Features */}
                           <div className="space-y-3">
                              <div className="font-medium text-sm">{t.featuresSection}</div>
                              <div className="grid w-full max-w-md items-center gap-1.5">
                                 <label htmlFor="feature-version-update" className="text-sm font-medium">arxiv_version_update_behavior</label>
                                 <input
                                    id="feature-version-update"
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                    value={getNestedValue(globalConfig, ['features', 'arxiv_version_update_behavior'], '')}
                                    onChange={e => updatePath(['features', 'arxiv_version_update_behavior'], e.target.value)}
                                    placeholder="append_notice"
                                 />
                              </div>
                           </div>

                           {/* Raw YAML */}
                           <div className="space-y-2">
                              <label htmlFor="raw-yaml" className="font-medium text-sm">{t.rawYaml}</label>
                              <textarea
                                 id="raw-yaml"
                                 className="min-h-64 w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
                                 value={rawContent}
                                 onChange={e => {
                                    const nextRaw = e.target.value
                                    setRawContent(nextRaw)
                                    try {
                                       const parsed = yaml.load(nextRaw)
                                       if (typeof parsed === 'object' && parsed) {
                                          setGlobalConfig(parsed)
                                          setYamlError('')
                                       } else {
                                          setYamlError('YAML parsed but is not a mapping object.')
                                       }
                                    } catch (err: any) {
                                       setYamlError(String(err?.message || err))
                                    }
                                 }}
                              />
                              {yamlError && <div className="text-xs text-destructive">{yamlError}</div>}
                           </div>
                        </CardContent>

                        <div className="p-6 pt-0 flex items-center gap-3">
                           <Button size="sm" onClick={handleSave} disabled={loading || !!yamlError}>
                              {loading ? <RefreshCw className="h-4 w-4 animate-spin"/> : <Save className="h-4 w-4 mr-2"/>}
                              {t.save}
                           </Button>
                           <div className="text-xs text-muted-foreground">{t.saveHintActions}</div>
                        </div>
            </Card>
        </div>
     </div>
   )
}
