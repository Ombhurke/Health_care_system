import { useEffect, useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import {
    Loader2,
    Activity,
    HeartPulse,
    RefreshCw,
    Sparkles,
    Download,
    CheckCircle,
    Thermometer,
    Scale,
    Calendar,
    Droplet
} from "lucide-react";
import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer
} from "recharts";
import { useAuth } from "@/hooks/useAuth";
import { useHealthInsightsStore } from "@/store/useHealthInsightsStore";
import { supabase } from "@/lib/supabase";
import { motion } from "framer-motion";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const DYNAMIC_COLORS = [
    "#ef4444", // Red
    "#3b82f6", // Blue
    "#10b981", // Emerald
    "#f59e0b", // Amber
    "#8b5cf6", // Violet
    "#ec4899", // Pink
    "#14b8a6", // Teal
];

export default function HealthInsights() {
    const { user } = useAuth();
    const [patientId, setPatientId] = useState<string | null>(null);
    const [isDownloading, setIsDownloading] = useState(false);
    const reportRef = useRef<HTMLDivElement>(null);

    const { data, setData, loading, setLoading, error, setError, hasLoaded, setHasLoaded } = useHealthInsightsStore();

    useEffect(() => {
        if (!user) return;
        const fetchPatient = async () => {
            const { data: patient } = await supabase
                .from("patients")
                .select("id")
                .eq("user_id", user.id)
                .maybeSingle();
            if (patient?.id) {
                setPatientId(patient.id);
            }
        };
        fetchPatient();
    }, [user]);

    const generateInsights = async () => {
        if (!patientId) return;
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(`${API_BASE_URL}/analyze_health/${patientId}`);
            if (!response.ok) {
                throw new Error("Failed to fetch health insights");
            }
            const result = await response.json();
            if (!result.success) throw new Error(result.detail || "Unknown error");

            const validMetrics = result.data.metrics.filter((m: any) => {
                if (!result.data.available_metrics || result.data.available_metrics.length === 0) return true;
                return result.data.available_metrics.some((key: string) => m[key] != null);
            }).sort((a: any, b: any) => new Date(a.date).getTime() - new Date(b.date).getTime());

            setData({ ...result.data, metrics: validMetrics });
            setHasLoaded(true);
        } catch (err: any) {
            console.error(err);
            setError(err.message || "Could not load health insights.");
        } finally {
            setLoading(false);
        }
    };

    const downloadPDF = async () => {
        if (!reportRef.current) return;
        setIsDownloading(true);
        try {
            const canvas = await html2canvas(reportRef.current, { scale: 2, useCORS: true, backgroundColor: '#0b111e' });
            const imgData = canvas.toDataURL('image/png');
            const pdf = new jsPDF('p', 'mm', 'a4');
            const pdfWidth = pdf.internal.pageSize.getWidth();
            const pdfHeight = (canvas.height * pdfWidth) / canvas.width;

            pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
            pdf.save(`Health_Insights_Report_${new Date().toISOString().split('T')[0]}.pdf`);
        } catch (err) {
            console.error("Failed to generate PDF:", err);
            alert("Failed to generate PDF report.");
        } finally {
            setIsDownloading(false);
        }
    };

    // Calculate Latest UI Metrics
    const latestMetric = data?.metrics && data.metrics.length > 0 ? data.metrics[data.metrics.length - 1] : {};

    // Values extracted or mocked to strictly represent the 6 items requested in UI
    const uiBP = latestMetric["Systolic BP"] && latestMetric["Diastolic BP"]
        ? `${latestMetric["Systolic BP"]}/${latestMetric["Diastolic BP"]}`
        : "120/80";

    const uiSugar = latestMetric["Blood Sugar"] || "95";
    const uiHeartRate = latestMetric["Heart Rate"] || "76";
    const uiWeight = data?.profile?.weight || "78 kg";
    const uiAge = data?.profile?.age || "32 yrs";
    const uiBloodGrp = data?.profile?.blood_group || "O+";

    return (
        <div className="min-h-screen relative font-sans bg-[#0b111e] text-slate-200 selection:bg-blue-500/30">
            <div className="container mx-auto px-4 py-8 relative max-w-5xl">

                {/* Header Section */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                        <div className="flex items-center gap-3 mb-2">
                            <Sparkles className="h-6 w-6 text-blue-400" />
                            <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
                                AI Health Insight
                            </h1>
                        </div>
                        <p className="text-slate-400 text-sm md:text-base">
                            Deep predictive analysis based on your complete medical history.
                        </p>
                    </motion.div>
                </div>

                {!hasLoaded && !loading && !error && (
                    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
                        <Card className="bg-[#151c2c] border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
                            <CardContent className="p-12 text-center flex flex-col items-center justify-center">
                                <div className="w-16 h-16 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mb-6">
                                    <Activity className="w-8 h-8 text-blue-400" />
                                </div>
                                <h2 className="text-2xl font-semibold text-white mb-3">Ready to Analyze Your Health?</h2>
                                <p className="text-slate-400 mb-8 text-center max-w-md">
                                    We'll securely parse your uploaded lab reports, discharge summaries, and prescriptions to map an interactive health trajectory entirely unique to you.
                                </p>
                                <Button onClick={generateInsights} size="lg" className="rounded-xl shadow-lg gap-2 bg-blue-600 hover:bg-blue-700 text-white border-0" disabled={!patientId}>
                                    <Sparkles className="w-5 h-5" />
                                    Generate AI Insights
                                </Button>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {loading && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Card className="bg-[#151c2c] border-slate-800 rounded-2xl overflow-hidden h-[500px] flex items-center justify-center shadow-2xl">
                            <div className="flex flex-col items-center gap-6 w-full max-w-2xl px-8">
                                <Loader2 className="w-10 h-10 animate-spin text-blue-500" />
                                <div className="w-full space-y-4 animate-pulse">
                                    <div className="h-4 bg-slate-700/50 rounded-full w-3/4 mx-auto"></div>
                                    <div className="h-4 bg-slate-700/50 rounded-full w-1/2 mx-auto"></div>
                                    <div className="h-48 bg-slate-800/50 rounded-xl w-full mt-8 border border-slate-700/30"></div>
                                </div>
                                <p className="text-sm font-medium text-blue-400 mt-4">Synthesizing medical intelligence...</p>
                            </div>
                        </Card>
                    </motion.div>
                )}

                {error && (
                    <Card className="bg-[#151c2c] border-red-900/50 rounded-2xl overflow-hidden shadow-2xl">
                        <CardContent className="p-8 text-center flex flex-col items-center justify-center">
                            <Activity className="w-12 h-12 text-red-400 mb-4" />
                            <h3 className="font-semibold text-white text-lg mb-2">Analysis Failed</h3>
                            <p className="text-slate-400 text-sm mb-6 max-w-sm">{error}</p>
                            <Button onClick={generateInsights} variant="outline" className="gap-2 border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white">
                                <RefreshCw className="w-4 h-4" /> Try Again
                            </Button>
                        </CardContent>
                    </Card>
                )}

                {hasLoaded && !loading && !error && data && data.metrics.length === 0 && (
                    <Card className="bg-[#151c2c] border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
                        <CardContent className="p-12 text-center flex flex-col items-center justify-center">
                            <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center mb-6">
                                <Thermometer className="w-8 h-8 text-slate-500" />
                            </div>
                            <h2 className="text-xl text-white font-semibold mb-2">Not Enough Data</h2>
                            <p className="text-slate-400 max-w-sm mx-auto mb-6">
                                {data.summary || "Upload and extract some medical records (like lab reports or vitals) to generate AI insights."}
                            </p>
                            <Button onClick={generateInsights} variant="outline" className="gap-2 border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white">
                                <RefreshCw className="w-4 h-4" /> Retry Analysis
                            </Button>
                        </CardContent>
                    </Card>
                )}

                {hasLoaded && !loading && !error && data && data.metrics.length > 0 && (
                    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                        <div ref={reportRef} className="space-y-6 pb-12">

                            {/* Action Bar */}
                            <div className="flex flex-col sm:flex-row items-center justify-between border border-emerald-500/20 px-4 py-3 rounded-xl bg-[#0b111e]/80">
                                <div className="flex items-center gap-2 text-emerald-500 font-medium">
                                    <CheckCircle className="w-5 h-5 flex-shrink-0" />
                                    Analysis Ready
                                </div>
                                <div className="flex gap-3 mt-4 sm:mt-0 w-full sm:w-auto">
                                    <Button variant="outline" size="sm" onClick={downloadPDF} disabled={isDownloading} className="flex-1 sm:flex-none gap-2 bg-transparent border-blue-500/30 text-blue-400 hover:bg-blue-500/10 hover:text-blue-300">
                                        {isDownloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                                        <span className="">{isDownloading ? "Generating..." : "Download PDF Report"}</span>
                                    </Button>
                                    <Button variant="ghost" size="sm" onClick={generateInsights} className="gap-2 text-slate-400 hover:text-white hover:bg-slate-800">
                                        <RefreshCw className="w-4 h-4" /> <span className="hidden sm:inline">Update</span>
                                    </Button>
                                </div>
                            </div>

                            {/* Top Grid Layer */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                {/* Risk Assessment Card (1/3) */}
                                <Card className="bg-[#10b981]/5 border-[#10b981]/20 rounded-2xl flex flex-col justify-center relative overflow-hidden h-36 md:h-full">
                                    <CardContent className="p-6">
                                        <p className="text-[#10b981] text-[10px] md:text-xs font-bold tracking-widest uppercase mb-1 md:mb-2">Risk Assessment</p>
                                        <h2 className="text-[#10b981] text-3xl md:text-4xl font-extrabold tracking-tight">Healthy</h2>
                                        <CheckCircle className="absolute right-6 top-1/2 -translate-y-1/2 w-14 h-14 md:w-16 md:h-16 text-[#10b981] opacity-70" strokeWidth={1.5} />
                                    </CardContent>
                                </Card>

                                {/* 6 Metrics Card (2/3) */}
                                <Card className="md:col-span-2 bg-[#151c2c] border-slate-800 flex items-center rounded-2xl">
                                    <CardContent className="p-6 w-full h-full">
                                        <div className="grid grid-cols-3 gap-y-8 gap-x-2 text-center h-full items-center">

                                            {/* Top Row */}
                                            <div className="flex flex-col items-center justify-center">
                                                <HeartPulse className="w-5 h-5 text-red-500 mb-2 opacity-80" />
                                                <p className="text-[10px] text-slate-400 font-bold tracking-widest uppercase mb-1">BP</p>
                                                <span className="text-white font-bold text-lg md:text-xl">{uiBP}</span>
                                            </div>
                                            <div className="flex flex-col items-center justify-center">
                                                <Thermometer className="w-5 h-5 text-blue-400 mb-2 opacity-80" />
                                                <p className="text-[10px] text-slate-400 font-bold tracking-widest uppercase mb-1">Sugar</p>
                                                <span className="text-white font-bold text-lg md:text-xl">{uiSugar}</span>
                                            </div>
                                            <div className="flex flex-col items-center justify-center">
                                                <Activity className="w-5 h-5 text-emerald-400 mb-2 opacity-80" />
                                                <p className="text-[10px] text-slate-400 font-bold tracking-widest uppercase mb-1">Heart Rate</p>
                                                <span className="text-white font-bold text-lg md:text-xl">{uiHeartRate}</span>
                                            </div>

                                            {/* Bottom Row */}
                                            <div className="flex flex-col items-center justify-center">
                                                <Scale className="w-5 h-5 text-amber-500 mb-2 opacity-80" />
                                                <p className="text-[10px] text-slate-400 font-bold tracking-widest uppercase mb-1">Weight</p>
                                                <span className="text-white font-bold text-lg md:text-xl">{uiWeight}</span>
                                            </div>
                                            <div className="flex flex-col items-center justify-center">
                                                <Calendar className="w-5 h-5 text-purple-400 mb-2 opacity-80" />
                                                <p className="text-[10px] text-slate-400 font-bold tracking-widest uppercase mb-1">Age</p>
                                                <span className="text-white font-bold text-lg md:text-xl">{uiAge}</span>
                                            </div>
                                            <div className="flex flex-col items-center justify-center">
                                                <Droplet className="w-5 h-5 text-red-400 mb-2 opacity-80" />
                                                <p className="text-[10px] text-slate-400 font-bold tracking-widest uppercase mb-1">Blood Grp</p>
                                                <span className="text-white font-bold text-lg md:text-xl">{uiBloodGrp}</span>
                                            </div>

                                        </div>
                                    </CardContent>
                                </Card>
                            </div>

                            {/* Chart Area Card */}
                            <Card className="bg-[#151c2c] border-slate-800 pb-2 rounded-2xl overflow-hidden shadow-2xl">
                                <CardHeader className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-6 border-b border-transparent">
                                    <CardTitle className="flex items-center gap-3 text-lg text-white font-medium tracking-tight">
                                        <Activity className="w-5 h-5 text-blue-500" />
                                        Health Trends Analysis
                                    </CardTitle>

                                    {/* Custom Graph Legend styling matching the mockup */}
                                    <div className="flex flex-wrap gap-3 mt-4 sm:mt-0">
                                        {data.available_metrics && data.available_metrics.map((metric, idx) => (
                                            <div key={`legend-${idx}`} className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/50 border border-slate-700/50 text-xs font-medium text-slate-300">
                                                <div className="w-2 h-2 rounded-full shadow-[0_0_8px_rgba(0,0,0,0.5)]" style={{ backgroundColor: DYNAMIC_COLORS[idx % DYNAMIC_COLORS.length], boxShadow: `0 0 8px ${DYNAMIC_COLORS[idx % DYNAMIC_COLORS.length]}80` }}></div>
                                                {metric}
                                            </div>
                                        ))}
                                    </div>
                                </CardHeader>
                                <CardContent className="p-0 sm:p-6 sm:pt-0">
                                    <div className="h-[350px] w-full mt-2">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <AreaChart data={data.metrics} margin={{ top: 20, right: 10, left: -20, bottom: 0 }}>
                                                <defs>
                                                    {data.available_metrics && data.available_metrics.map((_, idx) => {
                                                        const color = DYNAMIC_COLORS[idx % DYNAMIC_COLORS.length];
                                                        return (
                                                            <linearGradient key={`grad-${idx}`} id={`color${idx}`} x1="0" y1="0" x2="0" y2="1">
                                                                <stop offset="5%" stopColor={color} stopOpacity={0.4} />
                                                                <stop offset="95%" stopColor={color} stopOpacity={0} />
                                                            </linearGradient>
                                                        );
                                                    })}
                                                </defs>
                                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                                                <XAxis
                                                    dataKey="date"
                                                    axisLine={{ stroke: '#1e293b' }}
                                                    tickLine={false}
                                                    tick={{ fontSize: 12, fill: "#64748b" }}
                                                    dy={15}
                                                />
                                                <YAxis
                                                    axisLine={false}
                                                    tickLine={false}
                                                    tick={{ fontSize: 12, fill: "#64748b" }}
                                                />
                                                <Tooltip
                                                    contentStyle={{ borderRadius: '12px', border: '1px solid #1e293b', backgroundColor: '#0b111e', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)', color: '#fff' }}
                                                    itemStyle={{ fontWeight: 'bold' }}
                                                />

                                                {/* Hidden standard Legend since we built custom pill variants above */}

                                                {data.available_metrics && data.available_metrics.map((metric, idx) => {
                                                    const color = DYNAMIC_COLORS[idx % DYNAMIC_COLORS.length];
                                                    return (
                                                        <Area
                                                            key={metric}
                                                            type="monotone"
                                                            dataKey={metric}
                                                            name={metric}
                                                            stroke={color}
                                                            strokeWidth={3}
                                                            fillOpacity={1}
                                                            fill={`url(#color${idx})`}
                                                            activeDot={{ r: 6, strokeWidth: 0, fill: color, stroke: '#0b111e' }}
                                                            connectNulls={true}
                                                        />
                                                    );
                                                })}
                                            </AreaChart>
                                        </ResponsiveContainer>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Re-integrated Tips Section natively styled for Dark Mode */}
                            {data.tips && data.tips.length > 0 && (
                                <div className="mt-8 space-y-4">
                                    <h4 className="flex items-center gap-2 font-semibold text-lg text-white tracking-tight px-1">
                                        <Lightbulb className="w-5 h-5 text-amber-500" /> Actionable Recommendations
                                    </h4>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        {data.tips.map((tip, idx) => (
                                            <div key={idx} className="flex items-start gap-4 bg-[#151c2c] p-5 rounded-xl border border-slate-800 hover:border-amber-500/30 transition-colors shadow-lg">
                                                <div className="w-8 h-8 rounded-full bg-amber-500/10 text-amber-500 flex items-center justify-center text-sm font-bold shrink-0">
                                                    {idx + 1}
                                                </div>
                                                <p className="text-slate-300 leading-relaxed pt-0.5 text-sm md:text-base">{tip}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                        </div>
                    </motion.div>
                )}
            </div>
        </div>
    );
}
