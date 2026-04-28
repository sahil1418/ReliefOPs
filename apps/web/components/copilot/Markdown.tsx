"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("prose prose-sm max-w-none", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: ({ className, children, ...props }) => (
            <code
              className={cn(
                "rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.85em]",
                className,
              )}
              {...props}
            >
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="rounded-md bg-slate-900 p-3 text-xs text-slate-100">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="my-2 w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b px-2 py-1 text-left font-medium">{children}</th>
          ),
          td: ({ children }) => <td className="border-b px-2 py-1">{children}</td>,
          ul: ({ children }) => <ul className="list-disc pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5">{children}</ol>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
