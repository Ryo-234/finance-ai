"use client";

/**
 * 报告 Markdown 渲染器（轻量级，不依赖 react-markdown）
 *
 * 支持的 Markdown 语法：
 * - # / ## / ### 标题
 * - **粗体** / *斜体*
 * - - 无序列表
 * - 1. 有序列表
 * - > 引用块
 * - `行内代码`
 * - | 表格 |（带表头分隔行）
 * - --- 分割线
 * - 段落（空行分隔）
 */

import { cn } from "@/lib/utils";

interface ReportMarkdownProps {
  content: string;
  className?: string;
}

interface Block {
  type:
    | "h1"
    | "h2"
    | "h3"
    | "paragraph"
    | "list-item"
    | "quote"
    | "code"
    | "table"
    | "hr"
    | "blank";
  content?: string;
  level?: number; // 列表嵌套层级
  rows?: string[][]; // 表格行
}

function parseMarkdown(content: string): Block[] {
  const lines = content.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 标题
    const h3 = line.match(/^###\s+(.+)$/);
    if (h3) {
      blocks.push({ type: "h3", content: h3[1].trim() });
      i++;
      continue;
    }
    const h2 = line.match(/^##\s+(.+)$/);
    if (h2) {
      blocks.push({ type: "h2", content: h2[1].trim() });
      i++;
      continue;
    }
    const h1 = line.match(/^#\s+(.+)$/);
    if (h1) {
      blocks.push({ type: "h1", content: h1[1].trim() });
      i++;
      continue;
    }

    // 分割线
    if (/^---+$/.test(line.trim())) {
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    // 表格（| col | col | 形式 + 分隔行）
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      const tableLines: string[] = [];
      while (
        i < lines.length &&
        lines[i].trim().startsWith("|") &&
        lines[i].trim().endsWith("|")
      ) {
        tableLines.push(lines[i]);
        i++;
      }
      // 过滤分隔行 |---|---|
      const dataRows = tableLines.filter(
        (l) => !/^\|[\s-:|]+\|$/.test(l.trim())
      );
      if (dataRows.length > 0) {
        const parsedRows = dataRows.map((l) =>
          l
            .trim()
            .slice(1, -1)
            .split("|")
            .map((c) => c.trim())
        );
        blocks.push({ type: "table", rows: parsedRows });
      }
      continue;
    }

    // 引用
    if (line.startsWith("> ")) {
      blocks.push({ type: "quote", content: line.slice(2).trim() });
      i++;
      continue;
    }

    // 无序列表
    if (line.match(/^[-*]\s+/)) {
      const items: string[] = [];
      while (
        i < lines.length &&
        lines[i].match(/^[-*]\s+/)
      ) {
        items.push(lines[i].replace(/^[-*]\s+/, "").trim());
        i++;
      }
      items.forEach((item) => {
        blocks.push({ type: "list-item", content: item });
      });
      continue;
    }

    // 有序列表
    if (line.match(/^\d+\.\s+/)) {
      const items: string[] = [];
      while (
        i < lines.length &&
        lines[i].match(/^\d+\.\s+/)
      ) {
        items.push(lines[i].replace(/^\d+\.\s+/, "").trim());
        i++;
      }
      items.forEach((item, idx) => {
        blocks.push({ type: "list-item", content: `${idx + 1}. ${item}` });
      });
      continue;
    }

    // 空行
    if (line.trim() === "") {
      i++;
      continue;
    }

    // 普通段落（累积到下一个空行/标题/列表）
    let para = line;
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].match(/^[#>\-*]|^\d+\.|^\|/) &&
      !/^---+$/.test(lines[i].trim())
    ) {
      para += "\n" + lines[i];
      i++;
    }
    blocks.push({ type: "paragraph", content: para.trim() });
  }

  return blocks;
}

// 行内格式：粗体、斜体、代码、链接
function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  // 处理顺序：先粗体，再斜体，再代码，再链接
  const patterns: Array<{
    regex: RegExp;
    render: (match: string) => React.ReactNode;
  }> = [
    {
      // 链接 [text](url)
      regex: /\[([^\]]+)\]\(([^)]+)\)/g,
      render: (m) => {
        const match = m.match(/\[([^\]]+)\]\(([^)]+)\)/);
        if (!match) return m;
        return (
          <a
            key={key++}
            href={match[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-amber-600 hover:underline"
          >
            {match[1]}
          </a>
        );
      },
    },
    {
      // 粗体 **text**
      regex: /\*\*(.+?)\*\*/g,
      render: (m) => {
        const match = m.match(/\*\*(.+?)\*\*/);
        if (!match) return m;
        return (
          <strong key={key++} className="font-semibold text-gray-900">
            {match[1]}
          </strong>
        );
      },
    },
    {
      // 斜体 *text*（不与粗体冲突）
      regex: /(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g,
      render: (m) => {
        const match = m.match(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/);
        if (!match) return m;
        return (
          <em key={key++} className="italic">
            {match[1]}
          </em>
        );
      },
    },
    {
      // 行内代码 `code`
      regex: /`([^`]+)`/g,
      render: (m) => {
        const match = m.match(/`([^`]+)`/);
        if (!match) return m;
        return (
          <code
            key={key++}
            className="px-1.5 py-0.5 bg-gray-100 text-pink-600 rounded text-[0.9em] font-mono"
          >
            {match[1]}
          </code>
        );
      },
    },
  ];

  // 简单实现：依次处理（可能有嵌套但够用）
  let processed = remaining;
  for (const { regex, render } of patterns) {
    processed = processed.replace(regex, (m) => {
      const node = render(m);
      // 把 React node 暂时转成 placeholder 字符串
      return `__PLACEHOLDER_${parts.length}__`;
    });
    // 不行，这个方式不工作。直接用另一种方式：一次性处理
  }

  // 重写：一次性 scan
  return renderInlineOnce(text, key);
}

function renderInlineOnce(text: string, startKey = 0): React.ReactNode {
  // 找到所有 inline 格式的位置
  const regex =
    /(\*\*(.+?)\*\*)|(`([^`]+)`)|(\[(.+?)\]\((.+?)\))/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = startKey;
  let m;

  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIndex) {
      parts.push(text.slice(lastIndex, m.index));
    }
    if (m[1]) {
      // 粗体
      parts.push(
        <strong key={key++} className="font-semibold text-gray-900">
          {m[2]}
        </strong>
      );
    } else if (m[3]) {
      // 代码
      parts.push(
        <code
          key={key++}
          className="px-1.5 py-0.5 bg-gray-100 text-pink-600 rounded text-[0.9em] font-mono"
        >
          {m[4]}
        </code>
      );
    } else if (m[5]) {
      // 链接
      parts.push(
        <a
          key={key++}
          href={m[6]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-amber-600 hover:underline"
        >
          {m[5]}
        </a>
      );
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts.length > 0 ? parts : text;
}

export default function ReportMarkdown({ content, className }: ReportMarkdownProps) {
  const blocks = parseMarkdown(content);

  return (
    <div className={cn("report-markdown text-[15px] text-gray-700 space-y-3 leading-loose", className)}>
      {blocks.map((block, idx) => {
        switch (block.type) {
          case "h1":
            return (
              <h1
                key={idx}
                className="text-2xl font-bold text-gray-900 mt-6 mb-3 pb-2 border-b border-gray-200"
              >
                {block.content}
              </h1>
            );
          case "h2":
            return (
              <h2
                key={idx}
                className="text-xl font-semibold text-gray-800 mt-5 mb-2 pb-1.5 border-b border-gray-100"
              >
                {block.content}
              </h2>
            );
          case "h3":
            return (
              <h3
                key={idx}
                className="text-lg font-semibold text-gray-800 mt-4 mb-1.5"
              >
                {block.content}
              </h3>
            );
          case "paragraph":
            return (
              <p
                key={idx}
                className="text-gray-700 leading-loose"
                style={{ textIndent: "2em" }}
              >
                {renderInlineOnce(block.content || "")}
              </p>
            );
          case "list-item":
            return (
              <div
                key={idx}
                className="text-gray-700 leading-loose pl-2 flex gap-2"
              >
                <span className="text-amber-500 shrink-0">•</span>
                <span>{renderInlineOnce(block.content || "")}</span>
              </div>
            );
          case "quote":
            return (
              <blockquote
                key={idx}
                className="border-l-4 border-amber-300 bg-amber-50/50 pl-4 pr-3 py-2 my-2 text-gray-600 italic rounded-r leading-loose"
                style={{ textIndent: "2em" }}
              >
                {renderInlineOnce(block.content || "")}
              </blockquote>
            );
          case "code":
            return (
              <pre
                key={idx}
                className="bg-gray-900 text-gray-100 p-3 rounded-lg overflow-x-auto text-sm font-mono my-2"
              >
                {block.content}
              </pre>
            );
          case "hr":
            return <hr key={idx} className="my-4 border-gray-200" />;
          case "table": {
            const rows = block.rows || [];
            if (rows.length === 0) return null;
            return (
              <div
                key={idx}
                className="my-3 overflow-x-auto rounded-lg border border-gray-200"
              >
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-amber-50 border-b border-gray-200">
                      {rows[0].map((cell, j) => (
                        <th
                          key={j}
                          className="px-4 py-2 text-left font-semibold text-gray-700"
                        >
                          {renderInlineOnce(cell)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(1).map((row, ri) => (
                      <tr
                        key={ri}
                        className="border-b border-gray-100 hover:bg-gray-50"
                      >
                        {row.map((cell, ci) => (
                          <td
                            key={ci}
                            className="px-4 py-2 text-gray-700"
                          >
                            {renderInlineOnce(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }
          default:
            return null;
        }
      })}
    </div>
  );
}
