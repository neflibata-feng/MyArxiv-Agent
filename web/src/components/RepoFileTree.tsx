import { useEffect, useState } from 'react'
import { Folder, FileText, ChevronDown, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { GithubClient, RepoFile } from '@/lib/github'
import Fuse from 'fuse.js'

export interface RepoFileTreeProps {
  client: GithubClient
  rootPath: string
  selectedPath?: string | null
  onSelectFile: (file: RepoFile) => void
  searchTerm?: string
  fileFilter?: (file: RepoFile) => boolean
  loadingLabel?: string
}

function sortNodes(a: RepoFile, b: RepoFile) {
  if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
  return a.name.localeCompare(b.name)
}

function indentClass(depth: number) {
  const d = Math.max(0, Math.min(depth, 8))
  const classes = ['pl-2', 'pl-6', 'pl-10', 'pl-14', 'pl-18', 'pl-22', 'pl-26', 'pl-30', 'pl-34']
  return classes[d] || 'pl-2'
}

export function RepoFileTree({
  client,
  rootPath,
  selectedPath,
  onSelectFile,
  searchTerm,
  fileFilter,
  loadingLabel,
}: RepoFileTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set([rootPath]))
  const [childrenByPath, setChildrenByPath] = useState<Record<string, RepoFile[]>>({})
  const [loadingByPath, setLoadingByPath] = useState<Record<string, boolean>>({})

  const normalizedSearch = (searchTerm || '').trim().toLowerCase()

  const loadDir = async (path: string) => {
    setLoadingByPath(prev => ({ ...prev, [path]: true }))
    try {
      const res = await client.getDirContent(path)
      setChildrenByPath(prev => ({ ...prev, [path]: [...res].sort(sortNodes) }))
    } finally {
      setLoadingByPath(prev => ({ ...prev, [path]: false }))
    }
  }

  useEffect(() => {
    setExpanded(new Set([rootPath]))
    setChildrenByPath({})
    setLoadingByPath({})
    loadDir(rootPath)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, rootPath])

  const toggleDir = async (path: string) => {
    const next = new Set(expanded)
    if (next.has(path)) {
      next.delete(path)
      setExpanded(next)
      return
    }
    next.add(path)
    setExpanded(next)
    await loadDir(path)
  }

  const renderFile = (file: RepoFile, depth: number) => {
    if (fileFilter && !fileFilter(file)) return null
    const active = selectedPath === file.path
    return (
      <Button
        key={file.path}
        variant={active ? 'secondary' : 'ghost'}
        size="sm"
        className={cn('w-full justify-start h-8 px-2', indentClass(depth), active && 'bg-secondary')}
        onClick={() => onSelectFile(file)}
      >
        <FileText className="h-4 w-4 mr-2 text-muted-foreground" />
        <span className="truncate">{file.name}</span>
      </Button>
    )
  }

  const renderChildren = (path: string, depth: number) => {
    const children = childrenByPath[path] || []
    const isLoading = !!loadingByPath[path]

    const visibleChildren = (() => {
      if (!normalizedSearch) return children
      const dirs = children.filter(c => c.type === 'dir')
      const files = children.filter(c => c.type === 'file')
      const fuse = new Fuse(files, {
        includeScore: true,
        threshold: 0.35,
        ignoreLocation: true,
        keys: ['name'],
      })
      const matchedFiles = fuse.search(normalizedSearch).map(r => r.item)
      return [...dirs, ...matchedFiles]
    })()

    return (
      <div>
        {isLoading && (
          <div className={cn('text-xs text-muted-foreground px-2 py-1', indentClass(depth))}>
            {loadingLabel || 'Loading...'}
          </div>
        )}

        {visibleChildren.map(child => {
          if (child.type === 'dir') return renderNode(child.path, depth)
          return renderFile(child, depth)
        })}
      </div>
    )
  }

  const renderNode = (path: string, depth: number): React.ReactNode => {
    const isOpen = expanded.has(path)
    return (
      <div key={path}>
        <Button
          variant="ghost"
          size="sm"
          className={cn('w-full justify-start h-8 px-2', indentClass(depth))}
          onClick={() => toggleDir(path)}
        >
          {isOpen ? (
            <ChevronDown className="h-4 w-4 mr-1 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 mr-1 text-muted-foreground" />
          )}
          <Folder className="h-4 w-4 mr-2 text-muted-foreground" />
          <span className="truncate">{path === rootPath ? path : path.split('/').pop()}</span>
        </Button>

        {isOpen && renderChildren(path, depth + 1)}
      </div>
    )
  }

  return (
    <div className="w-full">
      {renderNode(rootPath, 0)}
    </div>
  )
}
