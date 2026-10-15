import { Fragment } from "react";

// Matches **bold** and [[source-id]] citation markers.
const INLINE_RE = /(\*\*[^*]+\*\*|\[\[[0-9a-fA-F-]{36}\]\])/g;

function SourceLink({ source, onOpenSource }) {
  return (
    <button
      type="button"
      className="source-link"
      title={source.topic_name}
      onClick={() => onOpenSource(source.topic_id, source.id)}
    >
      {source.title}, {source.date}
    </button>
  );
}

function Inline({ text, sourcesById, onOpenSource }) {
  return text.split(INLINE_RE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("[[")) {
      const source = sourcesById[part.slice(2, -2).toLowerCase()];
      return source ? <SourceLink key={i} source={source} onOpenSource={onOpenSource} /> : null;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

function parseBlocks(text) {
  const blocks = [];
  let list = null;
  for (const line of text.split("\n")) {
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        list = { type, items: [] };
        blocks.push(list);
      }
      list.items.push((bullet || numbered)[1]);
      continue;
    }
    list = null;
    if (heading) blocks.push({ type: "h", level: heading[1].length, text: heading[2] });
    else if (line.trim()) blocks.push({ type: "p", text: line });
  }
  return blocks;
}

// Minimal markdown renderer for AI answers (headings, lists, bold) that turns [[source-id]] markers into links.
export default function AnswerText({ text, sourcesById, onOpenSource }) {
  const inline = (t) => <Inline text={t} sourcesById={sourcesById} onOpenSource={onOpenSource} />;
  return (
    <div className="answer-text">
      {parseBlocks(text).map((block, i) => {
        if (block.type === "h") return <h5 key={i}>{inline(block.text)}</h5>;
        if (block.type === "p") return <p key={i}>{inline(block.text)}</p>;
        const List = block.type;
        return (
          <List key={i}>
            {block.items.map((item, j) => (
              <li key={j}>{inline(item)}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
