import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSlug from 'rehype-slug'
import rehypeAutolinkHeadings from 'rehype-autolink-headings'
import rehypeHighlight from 'rehype-highlight'
import rehypeExternalLinks from 'rehype-external-links'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'

const sanitizeSchema: any = {
  ...defaultSchema,
  tagNames: Array.from(
    new Set([
      ...(defaultSchema.tagNames || []),
      'details',
      'summary',
      'kbd',
      'mark',
    ])
  ),
  attributes: {
    ...(defaultSchema.attributes || {}),
    a: Array.from(new Set([...(defaultSchema.attributes?.a || []), 'target', 'rel'])),
    code: Array.from(new Set([...(defaultSchema.attributes?.code || []), 'className'])),
    span: Array.from(new Set([...(defaultSchema.attributes?.span || []), 'className'])),
    details: Array.from(new Set([...(defaultSchema.attributes?.details || []), 'open'])),
  },
}

export function MarkdownViewer({ content }: { content: string }) {
  return (
    <div className={[
      'prose dark:prose-invert max-w-none',
      'prose-headings:scroll-mt-16',
      'prose-a:text-primary prose-a:underline prose-a:underline-offset-4',
      'prose-hr:border-border',
      'prose-blockquote:border-border prose-blockquote:text-foreground',
      'prose-img:rounded-md prose-img:border prose-img:border-border',
      'prose-code:rounded prose-code:bg-muted/40 prose-code:px-1 prose-code:py-0.5',
      'prose-code:before:content-none prose-code:after:content-none',
      'prose-pre:overflow-x-auto prose-pre:rounded-md prose-pre:border prose-pre:border-border prose-pre:bg-muted/40 prose-pre:p-4',
      'prose-table:w-full',
    ].join(' ')}>
       <ReactMarkdown
         remarkPlugins={[remarkGfm, remarkMath]}
         rehypePlugins={[
           rehypeSlug,
           [rehypeAutolinkHeadings, { behavior: 'wrap' }],
           rehypeKatex,
           [rehypeExternalLinks, { target: '_blank', rel: ['noopener', 'noreferrer'] }],
           rehypeRaw,
           [rehypeSanitize, sanitizeSchema],
           rehypeHighlight,
         ]}
         components={{
           table: ({ children, ...props }) => (
             <div className="overflow-x-auto">
               <table className="w-full" {...props}>
                 {children}
               </table>
             </div>
           ),
           code: ({ className, children, ...props }: any) => {
             const isBlock = typeof className === 'string' && className.includes('language-')
             if (!isBlock) {
               return (
                 <code className={className} {...props}>
                   {children}
                 </code>
               )
             }
             return (
               <code className={[className, '!bg-transparent !p-0 block'].filter(Boolean).join(' ')} {...props}>
                 {children}
               </code>
             )
           },
         }}
       >
         {content}
       </ReactMarkdown>
    </div>
  )
}
