import { useEffect, useState } from "react";
import { api } from "../api";

// "Did you mean ...?" hints: existing tags that look like what the user is typing.
export default function TagSuggest({ text, exclude = [], onPick }) {
  const [similar, setSimilar] = useState([]);

  useEffect(() => {
    const query = text.trim();
    if (query.length < 2) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      api
        .similarTags(query)
        .then((result) => !cancelled && setSimilar(result))
        .catch(() => !cancelled && setSimilar([]));
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [text]);

  const visible = text.trim().length < 2 ? [] : similar.filter((t) => !exclude.includes(t.name));
  if (visible.length === 0) return null;

  return (
    <div className="tag-suggest">
      <span className="muted">האם התכוונת ל:</span>
      {visible.map((t) => (
        <button key={t.id} type="button" className="tag-chip tag-chip-suggest" onClick={() => onPick(t.name)}>
          #{t.name}
          <span className="muted"> ({t.count})</span>
        </button>
      ))}
    </div>
  );
}
