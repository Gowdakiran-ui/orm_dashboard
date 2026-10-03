import React, { useState, useMemo, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar
} from 'recharts';
import { Users, Activity, Search, UserPlus, AlertOctagon, X, Info, ExternalLink } from "lucide-react";
import { fetchDocumentDetails, searchExecutive, fetchReviewedExecutiveCandidates, addExecutiveCandidate } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, mutedText, bodyText } from "@/components/theme/tokens";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { isPlaceholderTitle, PreviewUnavailableLabel, PLACEHOLDER_ROW_CLASS } from "@/components/ui/PreviewUnavailable";
import { ExecutiveSentimentBreakdownDefinition, ExecutiveReputationGradeDefinition } from "@/lib/metricDefinitions";
import { executiveView, basedOnLine, eventsLabel, appearsInLine } from "@/utils/executivesView";

export interface ExecutivesTabProps {
  // Tracked executives that already have a stored score (the shared /executives list).
  executives: any[];
  clientId?: string | null;
  clientName?: string;
}

export function ExecutivesTab({ executives, clientId, clientName = "this client" }: ExecutivesTabProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const cardBorder = isDark ? "border-white/[0.12]" : "border-black/[0.06]";
  const rowBorder = isDark ? "border-white/[0.08]" : "border-black/[0.06]";
  const rowHoverBg = isDark ? "hover:bg-white/[0.04]" : "hover:bg-black/[0.02]";
  const surfaceBg = isDark ? "bg-black/30" : "bg-black/[0.03]";
  const surfaceBorder = isDark ? "border-white/[0.08]" : "border-black/[0.06]";
  const inputClass = isDark
    ? "bg-zinc-950/60 border border-white/[0.12] text-zinc-100 placeholder:text-zinc-600 focus:border-[#38BDF8]/50"
    : "bg-white/70 border border-black/[0.08] text-zinc-900 placeholder:text-zinc-400 focus:border-[#3B82F6]/50";
  const drawerSurface = isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.06]";
  const chipClass = isDark ? "bg-[#030712] border border-white/[0.10] text-zinc-400" : "bg-black/[0.03] border border-black/[0.08] text-zinc-500";
  const tableHeaderBg = isDark ? "bg-black/20" : "bg-black/[0.02]";
  const touchTarget = "min-h-[44px] inline-flex items-center justify-center";

  // ---- search (read-only: finds tracked executives and existing candidates, never creates anything) ----
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState<any | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchErrorMsg, setSearchErrorMsg] = useState<string | null>(null);

  // Switching client must not carry the previous client's text or result over.
  useEffect(() => {
    setSearchQuery("");
    setSearchResult(null);
    setSearchErrorMsg(null);
    setSelectedDocId(null);
  }, [clientId]);

  const runSearch = useCallback(async (raw: string) => {
    const query = raw.trim();
    if (!clientId || !query) return;
    setSearchLoading(true);
    setSearchErrorMsg(null);
    setSearchResult(null);
    try {
      setSearchResult(await searchExecutive(clientId, query));
    } catch (err: any) {
      setSearchErrorMsg(err?.message || "Search failed");
    } finally {
      setSearchLoading(false);
    }
  }, [clientId]);

  function handleExecutiveSearch(e: React.FormEvent) {
    e.preventDefault();
    runSearch(searchQuery);
  }

  function openByName(name: string) {
    setSearchQuery(name);
    runSearch(name);
  }

  const selectedExecutive = searchResult && searchResult.status === "tracked" ? searchResult.executive : null;
  const view = useMemo(() => (selectedExecutive ? executiveView(selectedExecutive) : null), [selectedExecutive]);
  const events: any[] = selectedExecutive?.events || [];
  const split = selectedExecutive?.sentiment_split || { positive: 0, neutral: 0, negative: 0 };
  const sentimentData = [
    { name: "Positive", value: split.positive, fill: "#10B981" },
    { name: "Neutral", value: split.neutral, fill: "#64748B" },
    { name: "Negative", value: split.negative, fill: "#EF4444" },
  ];

  // ---- details drawer (fields of the selected document only) ----
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedDocUrl, setSelectedDocUrl] = useState<string | null>(null);
  const selectedDoc = useMemo(() => events.find(d => d.id === selectedDocId) || null, [events, selectedDocId]);

  useEffect(() => {
    if (!selectedDocId || !clientId) {
      setSelectedDocUrl(null);
      return;
    }
    let cancelled = false;
    fetchDocumentDetails(clientId, selectedDocId)
      .then(details => { if (!cancelled) setSelectedDocUrl(details?.url || null); })
      .catch(() => { if (!cancelled) setSelectedDocUrl(null); });
    return () => { cancelled = true; };
  }, [selectedDocId, clientId]);

  // ---- candidate list (read-only) and the one-candidate Add ----
  const [candidates, setCandidates] = useState<any[]>([]);
  const [hiddenCount, setHiddenCount] = useState(0);
  const [candLoading, setCandLoading] = useState(false);
  const [candError, setCandError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<any | null>(null);
  const [adding, setAdding] = useState(false);
  const [addMessage, setAddMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const loadCandidates = useCallback(async () => {
    if (!clientId) return;
    setCandLoading(true);
    setCandError(null);
    try {
      const res = await fetchReviewedExecutiveCandidates(clientId);
      setCandidates(Array.isArray(res?.candidates) ? res.candidates : []);
      setHiddenCount(typeof res?.hidden_count === "number" ? res.hidden_count : 0);
    } catch (err: any) {
      setCandidates([]);
      setCandError(err?.message || "Could not load candidates");
    } finally {
      setCandLoading(false);
    }
  }, [clientId]);

  useEffect(() => { setAddMessage(null); setConfirming(null); loadCandidates(); }, [loadCandidates]);

  async function confirmAdd() {
    if (!clientId || !confirming || adding) return;   // a second click while the first request runs does nothing
    setAdding(true);
    try {
      const res = await addExecutiveCandidate(clientId, confirming.id);
      setAddMessage({ ok: res?.status === "added" || res?.status === "already_tracked", text: res?.message || "Done." });
      setConfirming(null);
      loadCandidates();
    } catch (err: any) {
      setAddMessage({ ok: false, text: err?.message || "Could not add this candidate." });
      setConfirming(null);
    } finally {
      setAdding(false);
    }
  }

  const trackedRows = (executives || []).filter(e => e && e.name);

  return (
    <div className="space-y-6">

      {/* SEARCH: finds executives the system already tracks or has already found. It cannot add anyone. */}
      <Card className={glassCard(theme)}>
        <CardHeader className={`pb-3 border-b ${cardBorder}`}>
          <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
            <Search className="h-4 w-4 text-[#38BDF8] mr-2" />
            Search Executives
          </CardTitle>
          <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>
            Finds people already tracked or already found in {clientName} coverage. Searching never adds anyone; use the candidate list below.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-4 space-y-4">
          <form onSubmit={handleExecutiveSearch} className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search executive name..."
              className={`flex-1 rounded px-3 py-2 text-xs font-mono focus:outline-none ${inputClass}`}
            />
            <button
              type="submit"
              disabled={searchLoading || !searchQuery.trim()}
              className={`bg-[#38BDF8] hover:bg-[#2ba8e0] disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold font-mono text-xs rounded px-4 whitespace-nowrap ${touchTarget}`}
            >
              {searchLoading ? "Searching..." : "Search"}
            </button>
          </form>

          {searchErrorMsg && <p className="text-red-500 font-mono text-xs">{searchErrorMsg}</p>}

          {searchResult && searchResult.status === "tracked" && view && selectedExecutive && (
            <div className={`border rounded p-4 space-y-2 ${surfaceBorder} ${surfaceBg}`}>
              <div className="flex items-center justify-between">
                <span className={`font-mono text-sm font-bold ${bodyText(theme)}`}>{selectedExecutive.name}</span>
                <div className="flex gap-2">
                  {view.badge === "low_evidence" && (
                    <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/30 font-mono text-xs">LOW EVIDENCE</Badge>
                  )}
                  <Badge className="bg-[#D4AF37]/10 text-[#D4AF37] border border-[#D4AF37]/30 font-mono text-xs">TRACKED</Badge>
                </div>
              </div>
              <p className={`text-xs font-mono ${mutedText(theme)}`}>{appearsInLine(clientName)}</p>
              {view.hasScore ? (
                <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                  <div>
                    <span className={`block ${mutedText(theme)}`}>Score</span>
                    <span className="text-[#D4AF37] font-bold text-sm">{view.scoreText}</span>
                  </div>
                  <div>
                    <span className={`flex items-center gap-1 ${mutedText(theme)}`}>
                      Grade
                      <InfoTooltip label="About Executive Reputation Grade"><ExecutiveReputationGradeDefinition /></InfoTooltip>
                    </span>
                    <span className={`font-bold ${view.badge === "low_evidence" ? "text-xs" : "text-sm"} ${bodyText(theme)}`}>{view.gradeText}</span>
                  </div>
                </div>
              ) : (
                <p className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>
                  No score yet. A score appears after a pipeline run finds coverage that mentions them together with {clientName}.
                </p>
              )}
              {view.hasScore && basedOnLine(selectedExecutive) && (
                <p className={`text-xs font-mono pt-1 border-t ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"} ${mutedText(theme)}`}>
                  {basedOnLine(selectedExecutive)}
                </p>
              )}
              {(view.asOfText || view.staleNote) && (
                <p className={`text-xs font-mono ${view.staleNote ? "text-amber-500" : mutedText(theme)}`}>
                  {view.staleNote ? view.staleNote : `As of ${view.asOfText}`}
                </p>
              )}
            </div>
          )}

          {searchResult && searchResult.status === "tracked_no_coverage" && (
            <div className={`border rounded p-4 space-y-1 ${surfaceBorder} ${surfaceBg}`}>
              <span className={`font-mono text-sm font-bold ${bodyText(theme)}`}>{searchResult.executive?.name}</span>
              <p className={`text-xs font-mono ${mutedText(theme)}`}>
                Tracked, but no coverage that mentions {searchResult.client_name || clientName} together with this person. There is nothing to score.
              </p>
            </div>
          )}

          {searchResult && searchResult.status === "unpromoted_candidate" && (
            <div className="border border-amber-500/30 rounded p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className={`font-mono text-sm font-bold ${bodyText(theme)}`}>{searchResult.candidate.name}</span>
                <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/30 font-mono text-xs">NOT YET TRACKED</Badge>
              </div>
              <p className={`text-xs font-mono ${mutedText(theme)}`}>
                Found in {clientName} coverage ({searchResult.candidate.mention_count} mentions, {(searchResult.candidate.confidence * 100).toFixed(0)}% confidence) but not tracked, so there is no reputation data. To track them, use the Add button in the candidate list below.
              </p>
            </div>
          )}

          {searchResult && searchResult.status === "ambiguous" && (
            <div className={`border rounded p-4 space-y-2 ${surfaceBorder} ${surfaceBg}`}>
              <p className={`text-xs font-mono ${mutedText(theme)}`}>
                {searchResult.total} people match {`"`}{searchQuery}{`"`}. Did you mean:
              </p>
              <div className="flex flex-wrap gap-2">
                {(searchResult.names || []).map((n: any) => (
                  <button
                    key={`${n.kind}-${n.name}`}
                    onClick={() => openByName(n.name)}
                    className={`text-xs font-mono rounded px-3 border ${surfaceBorder} ${bodyText(theme)} ${rowHoverBg} ${touchTarget}`}
                  >
                    {n.name} <span className={`ml-2 ${mutedText(theme)}`}>{n.kind === "tracked" ? "tracked" : "candidate"}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {searchResult && searchResult.status === "not_found" && (
            <p className={`text-xs font-mono ${mutedText(theme)}`}>
              No tracked executive or candidate matches {`"`}{searchQuery}{`"`}. Searching does not add people; only the candidate list below can.
            </p>
          )}

          {searchResult && searchResult.status === "invalid_name" && (
            <div className={`border rounded p-4 ${surfaceBorder} ${surfaceBg}`}>
              <p className={`text-xs font-mono ${mutedText(theme)}`}>
                This doesn{`'`}t look like a person{`'`}s name{searchResult.reason ? ` (${searchResult.reason})` : ""}.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* DETAIL of the selected executive, or the list of everyone tracked */}
      {selectedExecutive && view && view.hasScore ? (
        <>
          <Card className={glassCard(theme)}>
            <CardHeader>
              <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
                <Activity className="h-4 w-4 text-emerald-500 mr-2" />
                Sentiment Breakdown
                <InfoTooltip label="About Sentiment Breakdown"><ExecutiveSentimentBreakdownDefinition /></InfoTooltip>
              </CardTitle>
              <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>How the documents behind this score split by tone</CardDescription>
            </CardHeader>
            <CardContent className="h-[220px] pl-2">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sentimentData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                  <XAxis dataKey="name" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                  <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
                  <Bar dataKey="value" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card className={glassCard(theme)}>
            <CardHeader>
              <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
                <div className="flex items-center">
                  <Search className="h-4 w-4 text-[#38BDF8] mr-2" />
                  Documents Behind This Score {"—"} {selectedExecutive.name}
                </div>
                <Badge className="bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30 font-mono text-xs">
                  {eventsLabel(events.length)}
                </Badge>
              </CardTitle>
              <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>
                The documents from the last 30 days that were counted in this score. {"“"}Names them{"”"} says whether the full name is in the text.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader className={`${rowBorder} ${tableHeaderBg}`}>
                  <TableRow className={rowBorder}>
                    <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>HEADLINE</TableHead>
                    <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>BUSINESS TOPIC</TableHead>
                    <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>SOURCE</TableHead>
                    <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>PUBLISHED DATE</TableHead>
                    <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>NAMES THEM</TableHead>
                    <TableHead className={`font-mono text-xs text-right ${mutedText(theme)}`}>ACTION</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.map((doc) => {
                    const isPlaceholder = isPlaceholderTitle(doc.title, doc.source);
                    return (
                      <TableRow key={doc.id} className={`${rowBorder} ${rowHoverBg} transition-colors cursor-pointer ${isPlaceholder ? PLACEHOLDER_ROW_CLASS : ""}`} onClick={() => setSelectedDocId(doc.id)}>
                        <TableCell className={`font-mono text-xs max-w-[260px] truncate ${bodyText(theme)}`}>
                          {isPlaceholder ? <PreviewUnavailableLabel /> : doc.title}
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] font-mono text-xs bg-[#D4AF37]/5">{doc.topic}</Badge>
                        </TableCell>
                        <TableCell className={`font-mono text-xs truncate max-w-[100px] ${mutedText(theme)}`}>{doc.source}</TableCell>
                        <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>
                          {doc.timestamp ? new Date(doc.timestamp).toLocaleDateString(undefined, { dateStyle: 'short' }) : "N/A"}
                        </TableCell>
                        <TableCell className={`font-mono text-xs text-center ${doc.names_executive ? bodyText(theme) : "text-amber-500"}`}>
                          {doc.names_executive ? "Yes" : "No"}
                        </TableCell>
                        <TableCell className="text-right">
                          <button
                            onClick={(e) => { e.stopPropagation(); setSelectedDocId(doc.id); }}
                            className={`bg-blue-600 hover:bg-blue-700 cursor-pointer text-white font-mono text-xs rounded px-3 ${touchTarget}`}
                          >
                            Details
                          </button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {events.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className={`text-center py-10 font-mono text-xs ${mutedText(theme)}`}>
                        No documents were recorded behind this score.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      ) : (
        <Card className={glassCard(theme)}>
          <CardHeader className={`pb-3 border-b ${cardBorder}`}>
            <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
              <Users className="h-4 w-4 mr-2 opacity-70" />
              Tracked Executives
            </CardTitle>
            <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>
              People who appear in {clientName} coverage and have a stored score. Select one to see the documents behind the score.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-2">
            <Table>
              <TableHeader className={`${rowBorder} ${tableHeaderBg}`}>
                <TableRow className={rowBorder}>
                  <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>NAME</TableHead>
                  <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>SCORE</TableHead>
                  <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>GRADE</TableHead>
                  <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>DOCUMENTS</TableHead>
                  <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>AS OF</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trackedRows.map((e) => {
                  const v = executiveView(e);
                  return (
                    <TableRow key={e.entity_id || e.name} className={`${rowBorder} ${rowHoverBg} cursor-pointer`} onClick={() => openByName(e.name)}>
                      <TableCell className={`font-mono text-xs font-bold ${bodyText(theme)}`}>{e.name}</TableCell>
                      <TableCell className={`font-mono text-xs ${bodyText(theme)}`}>{v.scoreText}</TableCell>
                      <TableCell className={`font-mono text-xs ${bodyText(theme)}`}>
                        {v.badge === "low_evidence" ? <span className="text-amber-500">Low evidence {"—"} grade withheld</span> : v.gradeText}
                      </TableCell>
                      <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>{typeof e.document_count === "number" ? e.document_count : "-"}</TableCell>
                      <TableCell className={`font-mono text-xs ${v.staleNote ? "text-amber-500" : mutedText(theme)}`}>
                        {v.staleNote ?? v.asOfText ?? "-"}
                      </TableCell>
                    </TableRow>
                  );
                })}
                {trackedRows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className={`text-center py-8 font-mono text-xs ${mutedText(theme)}`}>
                      No tracked executive has a score yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* CANDIDATES: the only way to add an executive. Read-only list; each Add promotes exactly that one person. */}
      <Card className={glassCard(theme)}>
        <CardHeader className={`pb-3 border-b ${cardBorder}`}>
          <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
            <UserPlus className="h-4 w-4 text-[#D4AF37] mr-2" />
            Candidates Found In {clientName} Coverage
          </CardTitle>
          <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>
            Names the system found automatically. Those with a job title nearby and documents that also mention {clientName} come first. Adding one tracks that person only; a score appears once new coverage mentions them.
            {hiddenCount > 0 ? ` ${hiddenCount} names were hidden because they are not people or duplicate another name.` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-2 space-y-3">
          {addMessage && (
            <p className={`text-xs font-mono ${addMessage.ok ? "text-emerald-500" : "text-amber-500"}`}>{addMessage.text}</p>
          )}
          {candError && <p className="text-red-500 font-mono text-xs">{candError}</p>}
          <Table>
            <TableHeader className={`${rowBorder} ${tableHeaderBg}`}>
              <TableRow className={rowBorder}>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>NAME</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>MENTIONS</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>DOCUMENTS THAT ALSO MENTION {clientName.toUpperCase()}</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>JOB TITLE NEARBY</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>CONFIDENCE</TableHead>
                <TableHead className={`font-mono text-xs text-right ${mutedText(theme)}`}>ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {candidates.map((c) => (
                <TableRow key={c.id} className={`${rowBorder} ${rowHoverBg}`}>
                  <TableCell className={`font-mono text-xs font-bold ${bodyText(theme)}`}>
                    {c.name}
                    {Array.isArray(c.also_seen_as) && c.also_seen_as.length > 0 && (
                      <span className={`block font-normal ${mutedText(theme)}`}>also seen as {c.also_seen_as.join(", ")}</span>
                    )}
                  </TableCell>
                  <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>{c.mention_count}</TableCell>
                  <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>{c.client_documents} of {c.source_document_count}</TableCell>
                  <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>{c.title_nearby ? "Yes" : "No"}</TableCell>
                  <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>{(c.confidence * 100).toFixed(0)}%</TableCell>
                  <TableCell className="text-right">
                    <button
                      onClick={() => { setAddMessage(null); setConfirming(c); }}
                      className={`bg-[#D4AF37] hover:bg-[#bfa032] text-black font-bold font-mono text-xs rounded px-4 ${touchTarget}`}
                    >
                      Add
                    </button>
                  </TableCell>
                </TableRow>
              ))}
              {!candLoading && candidates.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className={`text-center py-8 font-mono text-xs ${mutedText(theme)}`}>
                    No candidates to review.
                  </TableCell>
                </TableRow>
              )}
              {candLoading && (
                <TableRow>
                  <TableCell colSpan={6} className={`text-center py-8 font-mono text-xs ${mutedText(theme)}`}>
                    Loading candidates...
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Confirmation for Add */}
      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center font-mono" role="dialog" aria-modal="true" aria-label="Confirm add executive">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => !adding && setConfirming(null)} />
          <div className={`relative w-[460px] max-w-[92vw] rounded border p-6 space-y-4 shadow-2xl ${drawerSurface} ${bodyText(theme)}`}>
            <h3 className="text-sm font-bold uppercase text-[#D4AF37]">Add {confirming.name}?</h3>
            <p className={`text-xs leading-relaxed ${mutedText(theme)}`}>
              This starts tracking {confirming.name} for {clientName}. Only this one person is added. No new searches are started. A score appears once new coverage mentions them.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirming(null)}
                disabled={adding}
                className={`bg-transparent border text-xs rounded px-4 ${mutedText(theme)} ${isDark ? "border-white/[0.12]" : "border-black/[0.08]"} ${touchTarget}`}
              >
                Cancel
              </button>
              <button
                onClick={confirmAdd}
                disabled={adding}
                className={`bg-[#D4AF37] hover:bg-[#bfa032] disabled:opacity-50 text-black font-bold text-xs rounded px-4 ${touchTarget}`}
              >
                {adding ? "Adding..." : "Confirm add"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Slide-over details drawer: this article's own fields only */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 overflow-hidden font-mono">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setSelectedDocId(null)} />
          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className={`w-[600px] backdrop-blur-2xl border-l flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-300 ${bodyText(theme)} ${drawerSurface}`}>

              <div className={`p-6 border-b flex items-center justify-between ${cardBorder}`}>
                <div className="flex items-center space-x-3">
                  <AlertOctagon className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-bold uppercase text-[#D4AF37]">Details</span>
                </div>
                <button
                  onClick={() => setSelectedDocId(null)}
                  className={`flex items-center gap-1.5 text-xs transition-colors ${mutedText(theme)} ${isDark ? "hover:text-zinc-100" : "hover:text-zinc-900"} ${touchTarget}`}
                >
                  <X className="h-5 w-5" />
                  <span>Close</span>
                </button>
              </div>

              <div className="flex-1 overflow-y-auto overflow-x-hidden p-6 space-y-6">
                <div className="space-y-2">
                  <h3 className={`text-sm font-bold leading-snug ${bodyText(theme)}`}>{selectedDoc.title}</h3>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Source: {selectedDoc.source}</span>
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Topic: {selectedDoc.topic}</span>
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>{selectedDoc.names_executive ? "Names this person" : "Does not name this person"}</span>
                  </div>
                </div>

                <div className={`p-4 rounded border border-red-500/20 space-y-3 ${surfaceBg}`}>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Risk of this article:</span>
                      <span className={bodyText(theme)}>{selectedDoc.risk ?? "-"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Sentiment of this article (-1 to +1):</span>
                      <span className={bodyText(theme)}>{typeof selectedDoc.sentiment === "number" ? selectedDoc.sentiment.toFixed(2) : "-"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Tone effect of this article:</span>
                      <span className="text-[#D4AF37] font-bold">{selectedDoc.reputation_impact ?? "-"}</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                    <Info className="h-3.5 w-3.5 mr-1 text-[#D4AF37]" /> Original Article Snippet
                  </span>
                  <div className={`border p-4 rounded text-xs leading-relaxed max-h-48 overflow-y-auto overflow-x-hidden whitespace-pre-wrap ${mutedText(theme)} ${surfaceBorder} ${surfaceBg}`}>
                    {selectedDoc.snippet || "No original content available."}
                  </div>
                </div>
              </div>

              <div className={`p-4 border-t flex justify-end space-x-3 ${cardBorder} ${isDark ? "bg-black/20" : "bg-black/[0.02]"}`}>
                {selectedDocUrl && (
                  <a
                    href={selectedDocUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`flex items-center space-x-1.5 bg-[#D4AF37] hover:bg-[#bfa032] text-black font-bold font-mono text-xs rounded px-4 ${touchTarget}`}
                  >
                    <span>View Source Article</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                <button
                  onClick={() => setSelectedDocId(null)}
                  className={`bg-transparent border text-xs rounded px-4 transition-colors ${mutedText(theme)} ${isDark ? "border-white/[0.12] hover:border-zinc-500 hover:text-zinc-100" : "border-black/[0.08] hover:border-zinc-400 hover:text-zinc-900"} ${touchTarget}`}
                >
                  Close
                </button>
              </div>

            </div>
          </div>
        </div>
      )}

    </div>
  );
}
