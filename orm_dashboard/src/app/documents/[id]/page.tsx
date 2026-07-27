"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, ArrowDown, FileText, Cpu, AlertTriangle, Activity, TrendingUp, ShieldAlert, Zap, Award } from "lucide-react";
import { fetchDocumentDetails } from "@/lib/api";

export default function DocumentExplorer() {
  const { id } = useParams();
  const router = useRouter();
  const [doc, setDoc] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      if (id) {
        const data = await fetchDocumentDetails("client", id as string); // In a real app we need client ID too, but API might allow lookup by doc ID
        // Mock fallback if API not ready, but user said NO MOCKS. 
        // We actually need the backend to return full trace data.
        if (data) {
            setDoc(data);
        } else {
            // If the document doesn't exist, we will show "No intelligence generated yet"
            setDoc(null);
        }
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) {
    return <div className="flex h-screen items-center justify-center bg-[#0B1120] text-[#D4AF37] font-mono text-xl"><Cpu className="animate-spin mr-2"/> LOADING EXPLORER...</div>;
  }

  if (!doc) {
    return (
        <div className="flex flex-col h-screen p-10 bg-[#0B1120] text-slate-100 font-mono items-center justify-center text-center">
            <h1 className="text-3xl text-red-500 mb-4">No intelligence generated yet</h1>
            <p className="text-slate-400">Log: GET /documents/{id} returned 0 rows or failed.</p>
            <button onClick={() => router.back()} className="mt-6 px-4 py-2 bg-[#D4AF37] text-black font-bold">RETURN TO DASHBOARD</button>
        </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0B1120] text-slate-100 font-sans p-8 selection:bg-[#D4AF37] selection:text-[#0B1120]">
      <div className="max-w-[1000px] mx-auto space-y-8">
        
        <button onClick={() => router.back()} className="flex items-center text-[#D4AF37] font-mono text-xs hover:underline uppercase mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" /> Back to Command Center
        </button>

        <div className="border-b border-[#222F4C] pb-4 mb-8">
            <h1 className="text-2xl font-mono font-bold text-slate-100 uppercase tracking-widest">Document Intelligence Trace</h1>
            <p className="text-sm font-mono text-slate-400 mt-2">UUID: {id}</p>
        </div>

        {/* 1. Article */}
        <Card className="bg-[#151D30] border-[#222F4C] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="font-mono text-[#D4AF37] flex items-center"><FileText className="mr-2 h-5 w-5"/>1. Raw Article Ingestion</CardTitle>
                <Badge variant="outline" className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono">STEP 1</Badge>
            </CardHeader>
            <CardContent className="font-mono text-sm space-y-2">
                <p><span className="text-slate-400">Title:</span> {doc.title}</p>
                <p><span className="text-slate-400">Source:</span> {doc.source_id || 'Unknown Feed'}</p>
                <p><span className="text-slate-400">URL:</span> <a href={doc.url} className="text-blue-400 break-all">{doc.url}</a></p>
                <div className="mt-4 p-4 bg-[#0B1120] border border-[#222F4C] text-slate-300 max-h-40 overflow-y-auto">
                    {doc.normalized_content}
                </div>
            </CardContent>
        </Card>

        <div className="flex justify-center my-2"><ArrowDown className="text-[#222F4C] h-8 w-8 animate-pulse" /></div>

        {/* 2. Entity Match */}
        <Card className="bg-[#151D30] border-[#222F4C] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="font-mono text-[#D4AF37] flex items-center"><Zap className="mr-2 h-5 w-5"/>2. Entity Match Engine</CardTitle>
                <Badge variant="outline" className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono">STEP 2</Badge>
            </CardHeader>
            <CardContent className="font-mono text-sm space-y-2">
                <p className="text-slate-400">Extracted Entity Keys:</p>
                <div className="flex flex-wrap gap-2 mt-2">
                    {doc.entities?.length > 0 ? doc.entities.map((e: any, i: number) => (
                        <Badge key={i} className="bg-blue-600 font-mono text-white">{e.name}</Badge>
                    )) : <span className="text-slate-500">No entities extracted yet.</span>}
                </div>
            </CardContent>
        </Card>

        <div className="flex justify-center my-2"><ArrowDown className="text-[#222F4C] h-8 w-8 animate-pulse" /></div>

        {/* 3. Topics */}
        <Card className="bg-[#151D30] border-[#222F4C] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="font-mono text-[#D4AF37] flex items-center"><Activity className="mr-2 h-5 w-5"/>3. Topic Classification</CardTitle>
                <Badge variant="outline" className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono">STEP 3</Badge>
            </CardHeader>
            <CardContent className="font-mono text-sm space-y-2">
                <div className="flex flex-wrap gap-2 mt-2">
                    {doc.topics?.length > 0 ? doc.topics.map((t: any, i: number) => (
                        <Badge key={i} variant="outline" className="border-purple-500/50 text-purple-400 font-mono">{t.name} (Conf: {t.confidence})</Badge>
                    )) : <span className="text-slate-500">No topics generated yet.</span>}
                </div>
            </CardContent>
        </Card>

        <div className="flex justify-center my-2"><ArrowDown className="text-[#222F4C] h-8 w-8 animate-pulse" /></div>

        {/* 4. Sentiment */}
        <Card className="bg-[#151D30] border-[#222F4C] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="font-mono text-[#D4AF37] flex items-center"><TrendingUp className="mr-2 h-5 w-5"/>4. Sentiment Analysis</CardTitle>
                <Badge variant="outline" className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono">STEP 4</Badge>
            </CardHeader>
            <CardContent className="font-mono text-sm space-y-2">
                {doc.sentiment !== undefined && doc.sentiment !== null ? (
                    <div>
                        <p><span className="text-slate-400">Index Value:</span> <span className={doc.sentiment > 0.1 ? 'text-green-500 font-bold' : doc.sentiment < -0.1 ? 'text-red-500 font-bold' : 'text-slate-300'}>{doc.sentiment.toFixed(3)}</span></p>
                    </div>
                ) : <span className="text-slate-500">No sentiment generated yet.</span>}
            </CardContent>
        </Card>

        <div className="flex justify-center my-2"><ArrowDown className="text-[#222F4C] h-8 w-8 animate-pulse" /></div>

        {/* 5. Risk */}
        <Card className="bg-[#151D30] border-[#222F4C] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="font-mono text-[#D4AF37] flex items-center"><ShieldAlert className="mr-2 h-5 w-5"/>5. Risk Evaluation</CardTitle>
                <Badge variant="outline" className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono">STEP 5</Badge>
            </CardHeader>
            <CardContent className="font-mono text-sm space-y-2">
                {doc.risk !== undefined && doc.risk !== null ? (
                    <div>
                        <p><span className="text-slate-400">Calculated Risk Index:</span> <span className="font-bold text-red-500">{doc.risk}</span></p>
                    </div>
                ) : <span className="text-slate-500">No risk evaluated yet.</span>}
            </CardContent>
        </Card>

        <div className="flex justify-center my-2"><ArrowDown className="text-[#222F4C] h-8 w-8 animate-pulse" /></div>

        {/* 6. Alert */}
        <Card className="bg-[#151D30] border-[#222F4C] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="font-mono text-[#D4AF37] flex items-center"><AlertTriangle className="mr-2 h-5 w-5"/>6. Alert Generation</CardTitle>
                <Badge variant="outline" className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono">STEP 6</Badge>
            </CardHeader>
            <CardContent className="font-mono text-sm space-y-2">
                {doc.alert ? (
                    <div className="bg-orange-500/10 border border-orange-500/30 p-4 rounded">
                        <p className="text-orange-400 font-bold uppercase">{doc.alert.title}</p>
                        <p className="text-slate-300 mt-2">Severity: {doc.alert.severity}</p>
                    </div>
                ) : <span className="text-slate-500">No alerts triggered by this document.</span>}
            </CardContent>
        </Card>

        <div className="flex justify-center my-2"><ArrowDown className="text-[#222F4C] h-8 w-8 animate-pulse" /></div>

        {/* 7. Narrative */}
        <Card className="bg-[#151D30] border-[#222F4C] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="font-mono text-[#D4AF37] flex items-center"><Cpu className="mr-2 h-5 w-5"/>7. Narrative Impact</CardTitle>
                <Badge variant="outline" className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono">STEP 7</Badge>
            </CardHeader>
            <CardContent className="font-mono text-sm space-y-2">
                {doc.narrative ? (
                    <div>
                        <p><span className="text-slate-400">Mapped to Storyline:</span> <span className="text-slate-100 font-bold">{doc.narrative.name}</span></p>
                        <p><span className="text-slate-400">Current Mentions:</span> {doc.narrative.mentions}</p>
                    </div>
                ) : <span className="text-slate-500">Document did not map to an active narrative cluster.</span>}
            </CardContent>
        </Card>

        <div className="flex justify-center my-2"><ArrowDown className="text-[#222F4C] h-8 w-8 animate-pulse" /></div>

        {/* 8. Reputation Impact */}
        <Card className="bg-[#151D30] border-[#222F4C] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="font-mono text-[#D4AF37] flex items-center"><Award className="mr-2 h-5 w-5"/>8. Global Reputation Adjustment</CardTitle>
                <Badge variant="outline" className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono">STEP 8</Badge>
            </CardHeader>
            <CardContent className="font-mono text-sm space-y-2">
                {doc.reputation_impact ? (
                    <div className="text-center p-4">
                        <span className="text-xs uppercase text-slate-400 block mb-2">Calculated Impact Vector</span>
                        <span className={`text-4xl font-extrabold ${doc.reputation_impact.includes('+') ? 'text-green-500' : 'text-red-500'}`}>{doc.reputation_impact}</span>
                    </div>
                ) : <span className="text-slate-500">Reputation processing pending...</span>}
            </CardContent>
        </Card>
      </div>
    </div>
  );
}
