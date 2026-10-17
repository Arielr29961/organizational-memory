"""How many characters of each source the model gets to read in Ask AI.

The old rule gave every source the same small slice (at most 3,000 characters), so a 30-minute transcript was cut after
a few minutes. Here the budget is shared fairly but unevenly: short sources are shown in full and what they do not use
goes to the long ones, up to a per-source cap.
"""


def allocate_chars(lengths: list[int], budget: int, cap: int) -> list[int]:
    """Characters to show of each source (same order as `lengths`): never more than the source has or `cap`, and in
    total never more than `budget`. Shorter sources are served first, so their unused share flows to the longer ones."""
    n = len(lengths)
    allocation = [0] * n
    remaining = budget
    left = n
    for i in sorted(range(n), key=lambda i: lengths[i]):
        share = remaining // left if left else 0
        allocation[i] = max(0, min(lengths[i], cap, share))
        remaining -= allocation[i]
        left -= 1
    return allocation


def clip(text: str, limit: int) -> str:
    """The first `limit` characters; when something was cut the text says so, so the model can tell the user."""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n[... התוכן קוצר: מוצגים {limit:,} מתוך {len(text):,} תווים ...]"
