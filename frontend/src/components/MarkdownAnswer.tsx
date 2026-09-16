import type { ReactElement, ReactNode } from "react";

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const tokens = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*\n]+\*)/g).filter(Boolean);
  return tokens.map((token, index) => {
    const key = `${keyPrefix}-${index}`;
    if (token.startsWith("**") && token.endsWith("**")) return <strong key={key}>{token.slice(2, -2)}</strong>;
    if (token.startsWith("`") && token.endsWith("`")) return <code key={key}>{token.slice(1, -1)}</code>;
    if (token.startsWith("*") && token.endsWith("*")) return <em key={key}>{token.slice(1, -1)}</em>;
    return <span key={key}>{token}</span>;
  });
}

function cleanNarrative(content: string): string {
  return content
    .replace(/\$(-?\d+(?:\.\d+)?)/g, (_match, value: string) => `$${Number(value).toFixed(2)}`)
    .replace(/(-?\d+\.\d{3,})%/g, (_match, value: string) => `${Number(value).toFixed(2)}%`)
    .replace(/\bPDL\d+\b/gi, "the selected pricing decision")
    .replace(/\bPRO\d+\b/gi, "the selected product")
    .replace(/\bSTO\d+\b/gi, "the selected store")
    .replace(/\bCAT\d+\b/gi, "the selected category")
    .replace(/\bCHANNEL\s*\|\s*([A-Za-z-]+)/gi, (_match, channel: string) => `${channel} channel`)
    .replace(/\bdynamic pricing\b/gi, "pricing strategy")
    .replace(/\bPricingDecisionID\b/gi, "pricing decision")
    .replace(/\bProductID\b/gi, "product")
    .replace(/\bStoreID\b/gi, "store")
    .replace(/\bCategoryID\b/gi, "category")
    .replace(/\bExpectedRevenue\b/gi, "expected revenue")
    .replace(/\bExpectedGrossProfit\b/gi, "expected gross profit")
    .replace(/\bFinalRecommendedPrice\b/gi, "recommended price")
    .replace(/\bFinalAction\b/gi, "recommended action")
    .replace(/\bmanual_review_flag\b/gi, "manual review")
    .replace(/Phase\s*6\s*Model[- ]Optimal\s*Price/gi, "Model recommendation")
    .replace(/Phase\s*7\s*Final\s*Recommended\s*Price/gi, "Final recommendation")
    .replace(/Phase\s*[0-9]+/gi, "")
    .replace(/Historical\s*AppliedPrice/gi, "Previous price")
    .replace(/CurrentPrice/gi, "Current price")
    .replace(/Model[- ]Optimal\s*Price/gi, "Model recommendation")
    .replace(/Final\s*Recommended\s*Price/gi, "Final recommendation")
    .replace(/\bPRICE_INCREASE\b/g, "price increase")
    .replace(/\bPRICE_DECREASE\b/g, "price decrease")
    .replace(/\bNO_CHANGE\b/g, "no change")
    .replace(/[ \t]{2,}/g, " ");
}

export function MarkdownAnswer({ content }: { content: string }): ReactElement {
  const lines = cleanNarrative(content).replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  const isTableSeparator = (line: string): boolean => /^\s*\|?\s*:?-{3,}/.test(line) && line.includes("|");
  const cells = (line: string): string[] => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const children = renderInline(heading[2], `heading-${index}`);
      blocks.push(heading[1].length === 1 ? <h2 key={`h-${index}`}>{children}</h2> : heading[1].length === 2 ? <h3 key={`h-${index}`}>{children}</h3> : <h4 key={`h-${index}`}>{children}</h4>);
      index += 1;
      continue;
    }
    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = cells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim().includes("|")) { rows.push(cells(lines[index])); index += 1; }
      blocks.push(<div className="markdown-table-wrap" key={`table-${index}`}><table className="markdown-table"><thead><tr>{headers.map((header, cellIndex) => <th key={cellIndex}>{renderInline(header, `th-${index}-${cellIndex}`)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, cellIndex) => <td key={cellIndex}>{renderInline(row[cellIndex] ?? "", `td-${rowIndex}-${cellIndex}`)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) { items.push(lines[index].trim().replace(/^[-*]\s+/, "")); index += 1; }
      blocks.push(<ul className="markdown-list" key={`ul-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item, `ul-${index}-${itemIndex}`)}</li>)}</ul>);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) { items.push(lines[index].trim().replace(/^\d+\.\s+/, "")); index += 1; }
      blocks.push(<ol className="markdown-list" key={`ol-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item, `ol-${index}-${itemIndex}`)}</li>)}</ol>);
      continue;
    }
    const paragraph = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s+/.test(lines[index].trim()) && !/^[-*]\s+/.test(lines[index].trim()) && !/^\d+\.\s+/.test(lines[index].trim()) && !(lines[index].includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]))) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={`p-${index}`}>{renderInline(paragraph.join(" "), `p-${index}`)}</p>);
  }
  return <div className="markdown-answer">{blocks}</div>;
}
