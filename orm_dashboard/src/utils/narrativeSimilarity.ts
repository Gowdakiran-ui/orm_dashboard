// Display-level "might be the same underlying story" hint for narrative cards.
// Reuses the same recipe narrative_engine.py already uses to cluster documents
// (title-token Jaccard + a day window), applied one level up across narrative
// names instead of document titles. This never merges narratives or changes
// clustering -- it's purely an inline note.
//
// narrative_engine.py's calculate_narratives builds narrative_name as either
// just the type label ("Labor Relations Narrative", when the topic had only
// one incident cluster this run) or "<type label> - <headline snippet>" (when
// it had several) -- see narrative_name/mapping['name']/title_snippet there.
// That " - " is a reliable structural split point: splitNarrativeName below
// isolates the generic type-prefix (near-universal on any client's names,
// e.g. "Electric Vehicle Narrative", "Executive Leadership Narrative") from
// the actual story-specific content that follows it, so only the latter is
// tokenized. This is a structural rule, not a hardcoded category list, so it
// applies identically to every client's narrative names.

const STOPWORDS = new Set([
  "the", "and", "for", "with", "from", "into", "over", "amid", "about", "this",
  "that", "narrative", "story", "coverage", "news", "report", "update", "new",
]);

function splitNarrativeName(name: string): { prefix: string; content: string } {
  const idx = name.indexOf(" - ");
  if (idx === -1) return { prefix: name, content: "" };
  return { prefix: name.slice(0, idx), content: name.slice(idx + 3) };
}

function tokenize(text: string, excludeTokens?: Set<string>): Set<string> {
  return new Set(
    (text || "")
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((t) => t.length > 2 && !STOPWORDS.has(t) && !(excludeTokens && excludeTokens.has(t)))
  );
}

// Only the story-specific content tokens count toward similarity: the
// generic type-prefix (split off structurally above) and the client's own
// name/brand (which appears in effectively every one of that client's
// narratives, so it can never be real signal) are both excluded first.
function contentTokens(name: string, clientNameTokens: Set<string>): Set<string> {
  const { content } = splitNarrativeName(name);
  return tokenize(content, clientNameTokens);
}

function jaccardSimilarity(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let intersection = 0;
  a.forEach((t) => {
    if (b.has(t)) intersection++;
  });
  const union = a.size + b.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

function sharedTokenCount(a: Set<string>, b: Set<string>): number {
  let intersection = 0;
  a.forEach((t) => {
    if (b.has(t)) intersection++;
  });
  return intersection;
}

// A flat minimum (e.g. "always >=3") breaks short-but-real matches: the
// real Anthropic "Innovation Narrative - ...Claude Fable 5.1 and Mythos"
// case only has 3 content tokens total, and shares just 2 of them with its
// genuine Product Launch/Market Position matches -- a flat >=3 floor would
// silently drop that real match. Scaling the requirement to the SHORTER
// narrative's own content-token count fixes this: short titles need fewer
// absolute shared tokens to be confident, longer ones need proportionally
// more, which is exactly what suppressed Tesla's remaining false positives
// (e.g. two unrelated "Elon Musk ..." headlines sharing only {elon, musk})
// without touching the real short-title match above (verified against both
// clients' live data -- see narrativeSimilarity's use in
// NarrativeIntelligenceWorkbench.tsx).
function minSharedTokensRequired(a: Set<string>, b: Set<string>): number {
  const smaller = Math.min(a.size, b.size);
  return Math.max(2, Math.ceil(smaller * 0.5));
}

// Started at the same 0.25 narrative_engine.py's document clustering uses
// for title-Jaccard membership; lowered to 0.2 after testing against real
// narrative names (Anthropic's live "Fable 5.1" cluster) -- 0.25 missed the
// Innovation <-> Product Launch pair (0.23) even though both were bridged
// by Market Position (0.31 / 0.38). Content-only tokenization (prefix +
// client name stripped) actually raises that same pair to ~0.22 rather than
// lowering it, so 0.2 still holds with the stricter token set.
export const RELATED_NARRATIVE_JACCARD_THRESHOLD = 0.2;
// A few days' proximity, matching the "few days" guidance -- loose enough
// that narratives detected on the same real-world event still line up even
// if their own last-document timestamps drift by a day or two.
export const RELATED_NARRATIVE_DAY_WINDOW = 5;

export interface RelatableNarrative {
  id: string;
  name: string;
  lastDetectedTs?: number | null;
}

export function findRelatedNarratives<T extends RelatableNarrative>(
  target: T,
  candidates: T[],
  clientName: string
): T[] {
  const clientNameTokens = tokenize(clientName);
  const targetTokens = contentTokens(target.name, clientNameTokens);
  if (targetTokens.size === 0) return [];
  const dayMs = 24 * 60 * 60 * 1000;

  return candidates.filter((other) => {
    if (other.id === target.id) return false;
    const otherTokens = contentTokens(other.name, clientNameTokens);
    const sim = jaccardSimilarity(targetTokens, otherTokens);
    if (sim < RELATED_NARRATIVE_JACCARD_THRESHOLD) return false;
    if (sharedTokenCount(targetTokens, otherTokens) < minSharedTokensRequired(targetTokens, otherTokens)) return false;
    if (target.lastDetectedTs && other.lastDetectedTs) {
      if (Math.abs(target.lastDetectedTs - other.lastDetectedTs) > RELATED_NARRATIVE_DAY_WINDOW * dayMs) {
        return false;
      }
    }
    return true;
  });
}
