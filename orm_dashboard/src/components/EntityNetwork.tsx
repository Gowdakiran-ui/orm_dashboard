import React, { useState, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Share2, Users, FileText } from "lucide-react";

export function EntityNetwork({ 
  documents, 
  executives, 
  narratives, 
  clientName,
  selectedNarrative,
  onSelectNarrative
}: { 
  documents: any[], 
  executives: any[], 
  narratives: any[], 
  clientName: string,
  selectedNarrative: string | null,
  onSelectNarrative: (name: string | null) => void
}) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [tooltipNode, setTooltipNode] = useState<any | null>(null);

  const WIDTH = 700;
  const HEIGHT = 460;
  const LEVEL_Y = { client: 50, executive: 150, narrative: 280, document: 400 };

  const { nodes, links } = useMemo(() => {
    const tempNodes: any[] = [];
    const tempLinks: any[] = [];

    const validExecutives = (executives || []).filter(e => e && e.id && e.name).slice(0, 6);
    const validNarratives = (narratives || []).filter(n => n && n.id && n.name).slice(0, 7);
    const topDocs = [...(documents || [])].filter(d => d && d.id && d.title).sort((a, b) => (b?.risk || 0) - (a?.risk || 0)).slice(0, 6);

    // Max mention count for scaling
    const maxMentions = Math.max(...validNarratives.map(n => n.mentions || 1), 1);

    // Level 0: Client (center)
    tempNodes.push({
      id: "client", label: clientName, type: "client",
      radius: 26, color: "#D4AF37",
      x: WIDTH / 2, y: LEVEL_Y.client,
      mentions: null
    });

    // Level 1: Executives — evenly spaced
    const execCount = validExecutives.length;
    validExecutives.forEach((exec, idx) => {
      const x = execCount === 1 ? WIDTH / 2 : 80 + (idx / (execCount - 1)) * (WIDTH - 160);
      tempNodes.push({
        id: `exec-${exec.id}`, label: exec.name, type: "executive",
        radius: 14, color: "#38BDF8",
        x, y: LEVEL_Y.executive,
        mentions: exec.mention_count ?? null
      });
      tempLinks.push({ source: "client", target: `exec-${exec.id}`, strength: 1.0, type: "exec" });
    });

    // Level 2: Narratives — sized by mention count
    const narrCount = validNarratives.length;
    validNarratives.forEach((narr, idx) => {
      const x = narrCount === 1 ? WIDTH / 2 : 80 + (idx / (narrCount - 1)) * (WIDTH - 160);
      const normMentions = (narr.mentions || 1) / maxMentions;
      const radius = 9 + normMentions * 12; // 9..21px based on mentions
      const strength = 0.3 + normMentions * 0.7;
      tempNodes.push({
        id: `narr-${narr.id}`, label: narr.name, type: "narrative",
        radius, color: "#A855F7",
        x, y: LEVEL_Y.narrative,
        mentions: narr.mentions || 0
      });
      // Connect to closest exec if any, otherwise client
      if (validExecutives.length > 0) {
        // link to nearest exec by position
        const nearestExec = tempNodes
          .filter(n => n.type === "executive")
          .reduce((best: any, n: any) => (!best || Math.abs(n.x - x) < Math.abs(best.x - x)) ? n : best, null);
        if (nearestExec) {
          tempLinks.push({ source: nearestExec.id, target: `narr-${narr.id}`, strength, type: "narr" });
        }
      } else {
        tempLinks.push({ source: "client", target: `narr-${narr.id}`, strength, type: "narr" });
      }
    });

    // Level 3: Top risk Documents — linked to matching narrative or fallback
    const docCount = topDocs.length;
    topDocs.forEach((doc, idx) => {
      const x = docCount === 1 ? WIDTH / 2 : 80 + (idx / (docCount - 1)) * (WIDTH - 160);
      tempNodes.push({
        id: `doc-${doc.id}`, label: doc.title, type: "document",
        radius: 9, color: "#EF4444",
        x, y: LEVEL_Y.document,
        docId: doc.id, mentions: null
      });
      const matchedNarr = validNarratives.find(n =>
        (doc.narrative && n.name.toLowerCase().includes(doc.narrative.toLowerCase())) ||
        (doc.topic && n.name.toLowerCase().includes(doc.topic.toLowerCase()))
      );
      const targetId = matchedNarr ? `narr-${matchedNarr.id}` : (validNarratives.length > 0 ? `narr-${validNarratives[0].id}` : "client");
      const strength = doc.risk ? doc.risk / 100 : 0.3;
      tempLinks.push({ source: targetId, target: `doc-${doc.id}`, strength, type: "doc" });
    });

    return { nodes: tempNodes, links: tempLinks };
  }, [documents, executives, narratives, clientName]);

  const hasContent = nodes.length > 1;

  if (!hasContent) {
    return (
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl overflow-hidden">
        <CardHeader>
          <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
            <Share2 className="h-4 w-4 text-[#D4AF37] mr-2" />
            Narrative Cluster Hierarchy
          </CardTitle>
          <CardDescription className="text-[10px] font-mono text-slate-500">Client → Executives → Narratives → Documents</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center bg-[#030712]/40 py-16 space-y-6">
          <div className="flex flex-col items-center space-y-3 opacity-60">
            {/* Mini hierarchy preview */}
            <div className="flex flex-col items-center space-y-2">
              <div className="h-7 w-7 rounded-full bg-[#D4AF37]/20 border border-[#D4AF37]/40 flex items-center justify-center">
                <div className="h-2 w-2 rounded-full bg-[#D4AF37]/50" />
              </div>
              <div className="h-4 w-px bg-[#1F2937]" />
              <div className="flex space-x-2">
                {[0,1,2].map(i => (
                  <div key={i} className="flex flex-col items-center space-y-1">
                    <div className="h-5 w-5 rounded-full bg-[#38BDF8]/20 border border-[#38BDF8]/30" />
                  </div>
                ))}
              </div>
              <div className="h-4 w-px bg-[#1F2937]" />
              <div className="flex space-x-2">
                {[0,1,2,3].map(i => (
                  <div key={i} className="h-4 w-4 rounded-full bg-[#A855F7]/20 border border-[#A855F7]/30" />
                ))}
              </div>
            </div>
          </div>
          <div className="text-center space-y-1">
            <p className="text-slate-400 font-mono text-xs font-bold uppercase tracking-wider">No Narrative Data Available</p>
            <p className="text-slate-600 font-mono text-[9px]">Entity hierarchy will render once executives, narratives, and documents are collected.</p>
          </div>
          <div className="flex items-center space-x-6 text-[9px] font-mono text-slate-600">
            <div className="flex items-center space-x-1.5"><div className="h-2.5 w-2.5 rounded-full bg-[#D4AF37]/40" /><span>Client</span></div>
            <div className="flex items-center space-x-1.5"><div className="h-2.5 w-2.5 rounded-full bg-[#38BDF8]/40" /><span>Executives</span></div>
            <div className="flex items-center space-x-1.5"><div className="h-2.5 w-2.5 rounded-full bg-[#A855F7]/40" /><span>Narratives</span></div>
            <div className="flex items-center space-x-1.5"><div className="h-2.5 w-2.5 rounded-full bg-[#EF4444]/40" /><span>Documents</span></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl overflow-hidden">
      <CardHeader>
        <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
          <Share2 className="h-4 w-4 text-[#D4AF37] mr-2" />
          Narrative Cluster Hierarchy
        </CardTitle>
        <CardDescription className="text-[10px] font-mono text-slate-500">
          Fixed hierarchy: Client → Executives → Narratives → Documents. Node size = mention volume. Edge thickness = relationship strength.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col bg-[#030712]/40 p-4 relative">
        {/* Level labels */}
        <div className="flex justify-between text-[8px] font-mono text-slate-600 uppercase tracking-widest px-4 mb-1">
          <span>CLIENT</span>
          <span>EXECUTIVES</span>
          <span>NARRATIVES</span>
          <span>DOCUMENTS</span>
        </div>
        <svg className="w-full" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} style={{ overflow: "visible" }}>
          <defs>
            <filter id="glow-hier-gold" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <filter id="glow-hier-blue" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="3" refY="2" orient="auto">
              <polygon points="0 0, 6 2, 0 4" fill="#1F2937" opacity="0.5" />
            </marker>
          </defs>

          {/* Horizontal level guide lines */}
          {Object.values(LEVEL_Y).map((y, i) => (
            <line key={i} x1={0} y1={y} x2={WIDTH} y2={y}
              stroke="#1F2937" strokeWidth="0.5" strokeDasharray="3 6" opacity="0.4" />
          ))}

          {/* Links */}
          {links.map((link, idx) => {
            const src = nodes.find(n => n.id === link.source);
            const tgt = nodes.find(n => n.id === link.target);
            if (!src || !tgt) return null;
            const isHovered = hoveredNode === link.source || hoveredNode === link.target;
            const isRelated = hoveredNode && (hoveredNode === link.source || hoveredNode === link.target);
            const opacity = hoveredNode ? (isRelated ? 0.85 : 0.08) : 0.35;
            const strokeColor = isHovered 
              ? (link.type === "exec" ? "#38BDF8" : link.type === "narr" ? "#A855F7" : "#EF4444")
              : "#334155";
            const strokeWidth = (link.strength || 0.3) * (isHovered ? 3 : 1.5);

            // Bezier curve for cleaner edges
            const mx = (src.x + tgt.x) / 2;
            const my = (src.y + tgt.y) / 2 - 10;
            return (
              <path
                key={idx}
                d={`M ${src.x} ${src.y} Q ${mx} ${my} ${tgt.x} ${tgt.y}`}
                stroke={strokeColor}
                strokeWidth={strokeWidth}
                strokeOpacity={opacity}
                fill="none"
                className="transition-all duration-300"
                markerEnd={isHovered ? "url(#arrowhead)" : undefined}
              />
            );
          })}

          {/* Nodes */}
          {nodes.map((node) => {
            const isDimmed = hoveredNode !== null && hoveredNode !== node.id && !links.some(l => (l.source === hoveredNode && l.target === node.id) || (l.source === node.id && l.target === hoveredNode));
            const opacity = isDimmed ? 0.2 : 1.0;
            const isClient = node.type === "client";
            const isSelected = selectedNarrative === node.label;
            const isHovered = hoveredNode === node.id;
            const glow = isClient ? "url(#glow-hier-gold)" : isHovered ? "url(#glow-hier-blue)" : undefined;

            return (
              <g
                key={node.id}
                transform={`translate(${node.x},${node.y})`}
                onMouseEnter={() => { setHoveredNode(node.id); setTooltipNode(node); }}
                onMouseLeave={() => { setHoveredNode(null); setTooltipNode(null); }}
                onClick={() => {
                  if (node.type === "narrative" && onSelectNarrative) {
                    onSelectNarrative(isSelected ? null : node.label);
                  }
                }}
                className="cursor-pointer transition-all duration-300"
                style={{ opacity }}
              >
                {/* Pulse ring for hovered or client */}
                {(isClient || isHovered) && (
                  <circle r={node.radius + 6} fill="none" stroke={node.color} strokeWidth="1" strokeOpacity="0.3"
                    className={isClient ? "animate-ping" : ""} style={{ animationDuration: "2s" }} />
                )}
                <circle
                  r={node.radius + (isSelected ? 3 : 0)}
                  fill={node.color}
                  fillOpacity={isClient || isSelected ? 0.85 : 0.15}
                  stroke={node.color}
                  strokeWidth={isSelected || isHovered ? 2.5 : 1.5}
                  filter={glow}
                />
                {/* Client center icon */}
                {isClient && (
                  <text textAnchor="middle" dominantBaseline="central" fontSize={10} fill="#D4AF37" fontWeight="bold" className="font-mono pointer-events-none">
                    ◆
                  </text>
                )}
                {/* Node label */}
                <text
                  y={node.radius + 11}
                  textAnchor="middle"
                  fill={isSelected ? "#D4AF37" : isHovered ? "#e2e8f0" : "#64748b"}
                  fontSize={node.type === "client" ? 9 : 7}
                  fontWeight={isClient || isSelected ? "bold" : "normal"}
                  className="font-mono pointer-events-none uppercase tracking-wider"
                >
                  {node.label.length > 16 ? `${node.label.substring(0, 13)}…` : node.label}
                </text>
                {/* Mention count badge for narratives */}
                {node.type === "narrative" && node.mentions > 0 && (
                  <text y={-node.radius - 4} textAnchor="middle" fill="#A855F7" fontSize={6} className="font-mono pointer-events-none">
                    {node.mentions}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {/* Legend */}
        <div className="flex items-center justify-center space-x-6 mt-2 text-[8px] font-mono text-slate-500 uppercase">
          <div className="flex items-center space-x-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-[#D4AF37]" />
            <span>Client</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-[#38BDF8]" />
            <span>Executive</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-[#A855F7]" />
            <span>Narrative (size = mentions)</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-[#EF4444]" />
            <span>Document</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <div className="h-0.5 w-5 bg-slate-500" style={{ height: "2px", borderTop: "1px solid", opacity: 0.6 }} />
            <span>edge weight = strength</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}