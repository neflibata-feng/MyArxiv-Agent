import { Octokit } from "octokit";

export interface Paper {
  id: string;
  title: string;
  originalLine: string;
  selected: boolean;
  raw: string;
  category?: string;
  authors?: string;
  date?: string;
  summary?: string;
  link?: string;
  type: 'normal' | 'update';
  group?: string;
  updateLog?: string;
}

export interface RepoFile {
  name: string;
  path: string;
  sha: string;
  type: "file" | "dir";
  download_url?: string | null;
}

export class GithubClient {
  private octokit: Octokit;
  private owner: string;
  private repo: string;
  private branch: string;
  private cache = new Map<string, { data: any, timestamp: number }>();
  private cacheTTL = 60 * 1000; // 1 minute cache
  
  constructor(token: string, owner: string, repo: string, branch: string = "main") {
    this.octokit = new Octokit({ auth: token });
    this.owner = owner;
    this.repo = repo;
    this.branch = branch;
  }

  clearCache() {
    this.cache.clear();
  }

  private getFromCache<T>(key: string): T | null {
    const item = this.cache.get(key);
    if (item && Date.now() - item.timestamp < this.cacheTTL) {
      return item.data as T;
    }
    return null;
  }

  private setCache(key: string, data: any) {
    this.cache.set(key, { data, timestamp: Date.now() });
  }

  async getUser() {
    const cacheKey = "user";
    const cached = this.getFromCache(cacheKey);
    if (cached) return cached;

    const { data } = await this.octokit.rest.users.getAuthenticated();
    this.setCache(cacheKey, data);
    return data;
  }

  async getRepoDetails() {
    const cacheKey = `repo/${this.owner}/${this.repo}`;
    const cached = this.getFromCache(cacheKey);
    if (cached) return cached;

    const { data } = await this.octokit.rest.repos.get({
      owner: this.owner,
      repo: this.repo,
    });
    this.setCache(cacheKey, data);
    return data;
  }

  async getFileContent(path: string, force = false): Promise<{ content: string; sha: string }> {
    const cacheKey = `file/${path}`;
    if (!force) {
        const cached = this.getFromCache<{ content: string; sha: string }>(cacheKey);
        if (cached) return cached;
    }

    try {
      const { data } = await this.octokit.rest.repos.getContent({
        owner: this.owner,
        repo: this.repo,
        path,
        ref: this.branch,
      });

      if (Array.isArray(data) || !('content' in data)) {
        throw new Error("Path is a directory, not a file");
      }

      const content = new TextDecoder().decode(
        Uint8Array.from(atob(data.content), (c) => c.charCodeAt(0))
      );
      
      const result = { content, sha: data.sha };
      this.setCache(cacheKey, result);
      return result;
    } catch (error) {
      console.error("Error fetching file:", error);
      throw error;
    }
  }

  async getDirContent(path: string, force = false): Promise<RepoFile[]> {
    const cacheKey = `dir/${path}`;
    if (!force) {
        const cached = this.getFromCache<RepoFile[]>(cacheKey);
        if (cached) return cached;
    }

    try {
      const { data } = await this.octokit.rest.repos.getContent({
        owner: this.owner,
        repo: this.repo,
        path,
        ref: this.branch,
      });

      if (!Array.isArray(data)) {
        throw new Error("Path is a file, not a directory");
      }

      const result = data.map((item: any) => ({
        name: item.name,
        path: item.path,
        sha: item.sha,
        type: item.type,
        download_url: item.download_url
      }));

      this.setCache(cacheKey, result);
      return result;
    } catch (error) {
       console.error("Error fetching dir:", error);
       return [];
    }
  }

  async updateFile(path: string, content: string, sha: string, message: string) {
    const contentBase64 = btoa(
      String.fromCharCode(...new TextEncoder().encode(content))
    );

    await this.octokit.rest.repos.createOrUpdateFileContents({
      owner: this.owner,
      repo: this.repo,
      path,
      message,
      content: contentBase64,
      sha,
      branch: this.branch,
    });
    
    // Invalidate cache
    this.cache.delete(`file/${path}`);
    const dir = path.split('/').slice(0, -1).join('/');
    if (dir) this.cache.delete(`dir/${dir}`);
  }

  async renderMarkdown(text: string): Promise<string> {
    try {
      const { data } = await this.octokit.rest.markdown.render({
        text,
        mode: "gfm",
        context: `${this.owner}/${this.repo}`
      });
      return data;
    } catch (e) {
      console.error(e);
      return text; 
    }
  }

  static parseInbox(markdown: string): Paper[] {
    const lines = markdown.split("\n");
    const papers: Paper[] = [];
    
    let state = 0;
    
    const hasDelimiter = lines.some(l => l.trim() === "---");
    if (!hasDelimiter) {
        state = 1;
    }

    let currentGroup = "默认";

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimLine = line.trim();
        
        if (state === 0) {
            if (trimLine === "---") {
                state = 1;
            }
            continue;
        }
        
        if (trimLine === "---") {
            continue;
        }

        if (trimLine.startsWith("## ")) {
            currentGroup = trimLine.replace(/^##\s*/, "");
            continue;
        }

        const match = trimLine.match(/^- \[(x| )\] (.*)/);
        if (match) {
            const isSelected = match[1] === "x";
            const rest = match[2];
            
            const updateMatch = rest.match(/^\(版本更新\)\s*(.*?)(?:\s*-\s*\[(.*?)\]\((.*?)\))?$/);
            
            if (rest.startsWith("(版本更新)")) {
                let id = Math.random().toString(36).substring(7);
                let title = "Unknown Title";
                let link = "";
                let logText = rest;

                const lastDashIndex = rest.lastIndexOf(" - [");
                if (lastDashIndex !== -1) {
                     logText = rest.substring(0, lastDashIndex).trim();
                     const linkPart = rest.substring(lastDashIndex + 3);
                     const linkMatch = linkPart.match(/^\[(.*?)\]\((.*?)\)/);
                     if (linkMatch) {
                         title = linkMatch[1];
                         link = linkMatch[2];
                         const idMatch = link.match(/arxiv\.org\/abs\/([^/]+)/);
                         if (idMatch) id = idMatch[1];
                     }
                } else {
                    const linkMatch = rest.match(/\[(.*?)\]\((.*?)\)/);
                    if (linkMatch) {
                        title = linkMatch[1];
                        link = linkMatch[2];
                    }
                }

                papers.push({
                    id,
                    title,
                    originalLine: line,
                    selected: isSelected,
                    raw: trimLine,
                    link,
                    type: 'update',
                    updateLog: logText,
                    group: currentGroup
                });

            } else {
                let title = "Unknown Title";
                let category = "Uncategorized";
                let link = "";
                let id = "";
                let authors = "";
                let date = "";
                let summary = "";

                const catMatch = rest.match(/^\*\*\[(.*?)\]\*\*/);
                if (catMatch) {
                    category = catMatch[1];
                }
                
                const linkStartIdx = rest.indexOf("[", catMatch ? catMatch[0].length : 0);
                if (linkStartIdx !== -1) {
                    const afterCat = rest.substring(linkStartIdx);
                    const linkMatch = afterCat.match(/^\[(.*?)\]\((.*?)\)/);
                    if (linkMatch) {
                        title = linkMatch[1];
                        link = linkMatch[2];
                        
                        const afterLink = afterCat.substring(linkMatch[0].length).trim();
                        const authorMatch = afterLink.match(/^\*by (.*?) \((.*?)\)\*/);
                        if (authorMatch) {
                            authors = authorMatch[1];
                            date = authorMatch[2];
                            
                            const afterAuthor = afterLink.substring(authorMatch[0].length).trim();
                            const summaryMatch = afterAuthor.match(/^-\s*_(.*)_$/);
                            if (summaryMatch) {
                                summary = summaryMatch[1];
                            } else if (afterAuthor.startsWith("-")) {
                                summary = afterAuthor.substring(1).trim();
                            }
                        }
                    }
                }

                if (title === "Unknown Title") {
                    const linkMatch = rest.match(/\[(.*?)\]\((.*?)\)/);
                    if (linkMatch) {
                        title = linkMatch[1];
                        link = linkMatch[2];
                    }
                    if (rest.includes("_")) {
                        summary = rest.substring(rest.indexOf("_")).replace(/_/g, "");
                    }
                }

                if (link) {
                    const idMatch = link.match(/arxiv\.org\/abs\/([^/]+)/);
                    if (idMatch) {
                        id = idMatch[1];
                    }
                }

                if (!id) id = Math.random().toString(36).substring(7);

                papers.push({
                    id,
                    title,
                    originalLine: line,
                    selected: isSelected,
                    raw: trimLine,
                    link,
                    category,
                    authors,
                    date,
                    summary,
                    type: 'normal',
                    group: currentGroup
                });
            }
        }
    }

    return papers;
  }

  static reconstructInbox(originalContent: string, papers: Paper[]): string {
    const lines = originalContent.split("\n");
    const newLines: string[] = [];
    
    const paperMap = new Map(papers.map(p => [p.id, p]));
    
    let state = 0;
    const hasDelimiter = lines.some(l => l.trim() === "---");
    if (!hasDelimiter) state = 1;

    for (let line of lines) {
        const trimLine = line.trim();
        
        if (state === 0) {
            newLines.push(line);
            if (trimLine === "---") {
                state = 1;
            }
            continue;
        }

        const match = trimLine.match(/^- \[(x| )\] (.*)/);
        if (match) { 
             let paperMatch: Paper | undefined;
             
             const linkMatch = trimLine.match(/arxiv\.org\/abs\/([^/)\s]+)/);
             if (linkMatch) {
                 const extractedId = linkMatch[1];
                 paperMatch = paperMap.get(extractedId);
                 if (!paperMatch) {
                     for (const p of papers) {
                         if (line.includes(p.id)) {
                             paperMatch = p;
                             break;
                         }
                     }
                 }
             }
             
             if (paperMatch) {
                 const checkState = paperMatch.selected ? "x" : " ";
                 const newLine = line.replace(/^- \[(x| )\]/, `- [${checkState}]`);
                 newLines.push(newLine);
             }
        } else {
            newLines.push(line);
        }
    }
    
    return newLines.join("\n");
  }
}
