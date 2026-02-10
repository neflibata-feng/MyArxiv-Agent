import React from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Github, Sun, Moon } from 'lucide-react'
import { Translation } from '@/i18n/locales'

interface LoginProps {
  t: Translation
  lang: 'zh' | 'en'
  setLang: (l: 'zh' | 'en') => void
  theme: 'light' | 'dark' | 'system'
  setTheme: (t: 'light' | 'dark' | 'system') => void
  repoStr: string
  setRepoStr: (s: string) => void
  token: string
  setToken: (s: string) => void
  handleLogin: () => void
}

export function Login({ 
  t, lang, setLang, theme, setTheme,
  repoStr, setRepoStr, token, setToken, handleLogin 
}: LoginProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-4 relative">
      <div className="absolute top-4 right-4 flex gap-2">
         <Button variant="ghost" size="sm" onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}>
           {lang === 'zh' ? 'EN' : '中'}
         </Button>
         <Button variant="ghost" size="sm" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
           {theme === 'dark' ? <Sun className="h-4 w-4"/> : <Moon className="h-4 w-4"/>}
         </Button>
      </div>
      <Card className="w-full max-w-sm shadow-xl border-t-4 border-t-primary">
         <CardHeader className="text-center">
            <Github className="mx-auto h-12 w-12 text-primary mb-4" />
            <CardTitle className="text-2xl">{t.welcome}</CardTitle>
            <p className="text-sm text-muted-foreground mt-2">{t.connectDesc}</p>
         </CardHeader>
         <CardContent className="space-y-4">
            <div className="space-y-2">
               <input 
                 className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background"
                 placeholder={t.repoPlaceholder}
                 value={repoStr}
                 onChange={e => setRepoStr(e.target.value)}
               />
               <input 
                 type="password"
                 className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background"
                 placeholder={t.tokenPrompt}
                 value={token}
                 onChange={e => setToken(e.target.value)}
               />
            </div>
            <Button className="w-full" onClick={handleLogin} disabled={!token || !repoStr}>
              {t.connect}
            </Button>
         </CardContent>
         <CardFooter className="justify-center text-xs text-muted-foreground">
            <a href="https://github.com/neflibata-feng" target="_blank" rel="noopener noreferrer" className="hover:underline">
               {t.copyright}
            </a>
         </CardFooter>
      </Card>
    </div>
  )
}
