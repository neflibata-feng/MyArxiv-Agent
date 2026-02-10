import React, { useState, useEffect } from 'react'
import { 
  BookOpen, Home, Calendar, Archive, Monitor, Settings,
  LogOut, Search
} from 'lucide-react'
import { GithubClient } from '@/lib/github'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import yaml from 'js-yaml'

// Components
import { Login } from '@/components/Login'
import { HomeView } from '@/views/Home'
import { InboxView } from '@/views/Inbox'
import { ArchiveView } from '@/views/Archive'
import { WorkbenchView } from '@/views/Workbench'
import { SettingsView } from '@/views/Settings'
import { I18N, Lang } from '@/i18n/locales'

type Tab = 'home' | 'inbox' | 'archive' | 'workbench' | 'settings'

function App() {
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>(() => (localStorage.getItem('app_theme') as any) || 'system')
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('app_lang') as Lang) || 'zh')
  const t = I18N[lang]

  const [token, setToken] = useState<string>(() => localStorage.getItem("github_token") || "")
  const [repoStr, setRepoStr] = useState<string>(() => localStorage.getItem('github_repo') || "")
  
  const [client, setClient] = useState<GithubClient | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('home')
  const [searchTerm, setSearchTerm] = useState("")
  const [config, setConfig] = useState<any>({})

  // Load repo config.yaml
  useEffect(() => {
    if (!client) return
    client
      .getFileContent('config.yaml')
      .then(res => {
        try {
          const parsed = yaml.load(res.content)
          if (typeof parsed === 'object' && parsed) setConfig(parsed)
          else setConfig({})
        } catch {
          setConfig({})
        }
      })
      .catch(() => setConfig({}))
  }, [client])

  // Theme Effect
  useEffect(() => {
    localStorage.setItem('app_theme', theme)
    const root = window.document.documentElement
    root.classList.remove('light', 'dark')
    if (theme === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      root.classList.add(systemTheme)
    } else {
      root.classList.add(theme)
    }
  }, [theme])

  useEffect(() => {
    localStorage.setItem('app_lang', lang)
  }, [lang])

  const connect = (repo: string, pat: string) => {
    if (!pat || !repo.includes('/')) return
    const parts = repo.split('/')
    if (parts.length < 2) return
    setClient(new GithubClient(pat, parts[0], parts[1]))
    localStorage.setItem('github_token', pat)
    localStorage.setItem('github_repo', repo)
  }

  // Auto-connect if saved token+repo are present
  useEffect(() => {
    if (client) return
    if (token && repoStr && repoStr.includes('/')) {
      connect(repoStr, token)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleLogin = () => {
    connect(repoStr, token)
  }
  
  const handleLogout = () => {
    setToken("")
    setRepoStr("")
    setClient(null)
    localStorage.removeItem("github_token")
    localStorage.removeItem("github_repo")
  }

  if (!client) {
    return (
      <Login 
        t={t}
        lang={lang} setLang={setLang}
        theme={theme} setTheme={setTheme}
        repoStr={repoStr} setRepoStr={setRepoStr}
        token={token} setToken={setToken}
        handleLogin={handleLogin}
      />
    )
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Top Nav */}
      <header className="sticky top-0 z-50 flex h-14 items-center border-b bg-background px-4 lg:px-6 gap-4">
        <h1 className="text-lg font-bold flex items-center gap-2 mr-4 hidden md:flex">
          <BookOpen className="h-5 w-5" /> {t.appTitle}
        </h1>
        
        <nav className="flex items-center gap-1 md:gap-2 flex-1 overflow-x-auto no-scrollbar">
           <NavButton icon={<Home/>} label={t.home} active={activeTab === 'home'} onClick={() => setActiveTab('home')} />
           <NavButton icon={<Calendar/>} label={t.inbox} active={activeTab === 'inbox'} onClick={() => setActiveTab('inbox')} />
           <NavButton icon={<Archive/>} label={t.archive} active={activeTab === 'archive'} onClick={() => setActiveTab('archive')} />
           <NavButton icon={<Monitor/>} label={t.workbench} active={activeTab === 'workbench'} onClick={() => setActiveTab('workbench')} />
        </nav>

        <div className="flex items-center gap-2 ml-auto">
           {/* Search Bar - Global */}
           <div className="relative hidden sm:block">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input 
                 className="h-9 w-40 lg:w-64 rounded-md border border-input bg-background pl-9 pr-4 text-sm"
                 placeholder={t.searchPlaceholder}
                 value={searchTerm}
                 onChange={(e) => setSearchTerm(e.target.value)}
              />
           </div>
           
           <Button variant="ghost" size="icon" onClick={() => setActiveTab('settings')} className={cn(activeTab==='settings' && "bg-accent")}>
             <Settings className="h-5 w-5" />
           </Button>
           
           <Button variant="ghost" size="icon" onClick={handleLogout}>
             <LogOut className="h-5 w-5" />
           </Button>
        </div>
      </header>
      
      {/* Main Content */}
      <main className="flex-1 overflow-hidden relative">
         {activeTab === 'home' && <HomeView client={client} config={config} />}
         {activeTab === 'inbox' && <InboxView client={client} t={t} searchTerm={searchTerm} />}
        {activeTab === 'archive' && <ArchiveView client={client} t={t} searchTerm={searchTerm} config={config} />}
        {activeTab === 'workbench' && <WorkbenchView client={client} t={t} searchTerm={searchTerm} config={config} />}
         {activeTab === 'settings' && <SettingsView client={client} t={t} appConfig={{theme, setTheme, lang, setLang}} globalConfig={config} setGlobalConfig={setConfig} />}
      </main>

      {/* Footer */}
      <footer className="border-t py-2 px-4 text-center text-xs text-muted-foreground bg-muted/20">
        <a href="https://github.com/neflibata-feng" target="_blank" rel="noopener noreferrer" className="hover:underline">
           {t.copyright}
         </a>
      </footer>
    </div>
  )
}

function NavButton({ icon, label, active, onClick }: any) {
  return (
    <Button 
      variant={active ? "secondary" : "ghost"} 
      size="sm" 
      onClick={onClick}
      className={cn("gap-2 h-9", active && "bg-secondary")}
    >
      {React.cloneElement(icon, { className: "h-4 w-4" })}
      <span className="hidden sm:inline-block">{label}</span>
    </Button>
  )
}

export default App

