import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Loader2, Activity, HeartPulse, RefreshCw, Lightbulb, Thermometer } from "lucide-react";
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend
} from "recharts";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface MetricData {
    date: string;
    systolic_bp?: number | null;
    diastolic_bp?: number | null;
    heart_rate?: number | null;
    blood_sugar?: number | null;
}

interface HealthData {
    summary: string;
    metrics: MetricData[];
    tips: string[];
}

export function HealthInsightsCard({ patientId }: { patientId: string }) {
    const [data, setData] = useState<HealthData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(`${API_BASE_URL}/analyze_health/${patientId}`);
            if (!response.ok) {
                throw new Error("Failed to fetch health insights");
            }
            const result = await response.json();
            if (!result.success) throw new Error(result.detail || "Unknown error");

            // Filter out metrics with completely null/undefined values to prevent strict recharts errors
            const validMetrics = result.data.metrics.filter(
                (m: MetricData) => m.systolic_bp != null || m.heart_rate != null || m.blood_sugar != null
            ).sort((a: MetricData, b: MetricData) => new Date(a.date).getTime() - new Date(b.date).getTime());

            setData({ ...result.data, metrics: validMetrics });
        } catch (err: any) {
            console.error(err);
            setError(err.message || "Could not load health insights.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (patientId) {
            fetchData();
        }
    }, [patientId]);

    if (loading) {
        return (
            <Card className="glass-card rounded-2xl overflow-hidden border-border/50 h-[450px] flex items-center justify-center">
                <div className="flex flex-col items-center gap-4 text-muted-foreground">
                    <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    <p className="text-sm font-medium">Analyzing your health records with AI...</p>
                </div>
            </Card>
        );
    }

    if (error) {
        return (
            <Card className="glass-card rounded-2xl overflow-hidden border-error/50">
                <CardContent className="p-8 text-center flex flex-col items-center justify-center">
                    <Activity className="w-12 h-12 text-error/50 mb-4" />
                    <h3 className="font-semibold text-lg mb-2">Analysis Failed</h3>
                    <p className="text-muted-foreground text-sm mb-6 max-w-sm">{error}</p>
                    <Button onClick={fetchData} variant="outline" className="gap-2">
                        <RefreshCw className="w-4 h-4" /> Try Again
                    </Button>
                </CardContent>
            </Card>
        );
    }

    if (!data || data.metrics.length === 0) {
        return (
            <Card className="glass-card rounded-2xl overflow-hidden border-border/50">
                <CardHeader className="pb-2 flex flex-row items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-lg font-heading">
                        <Activity className="w-5 h-5 text-primary" />
                        AI Health Insights
                    </CardTitle>
                    <Button variant="ghost" size="icon" onClick={fetchData} title="Refresh">
                        <RefreshCw className="w-4 h-4 text-muted-foreground" />
                    </Button>
                </CardHeader>
                <CardContent>
                    <div className="text-center py-12 rounded-xl bg-muted/30 border border-dashed border-border/60">
                        <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-3">
                            <Thermometer className="w-7 h-7 text-muted-foreground" />
                        </div>
                        <p className="font-medium text-foreground mb-1">Not Enough Data</p>
                        <p className="text-muted-foreground text-sm max-w-sm mx-auto">{data?.summary || "Upload and extract some medical records (like lab reports or vitals) to generate AI insights."}</p>
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="glass-card rounded-2xl overflow-hidden border-border/50 flex flex-col">
            <CardHeader className="pb-2 flex flex-row items-center justify-between border-b border-border/30 bg-muted/10">
                <CardTitle className="flex items-center gap-2 text-lg font-heading">
                    <HeartPulse className="w-5 h-5 text-red-500" />
                    AI Health Trajectory
                </CardTitle>
                <Button variant="ghost" size="icon" onClick={fetchData} title="Refresh Analysis">
                    <RefreshCw className="w-4 h-4 text-muted-foreground hover:rotate-180 transition-transform duration-500" />
                </Button>
            </CardHeader>

            <CardContent className="p-6 flex-1 flex flex-col gap-6">
                {/* Summary Statement */}
                <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 text-sm text-foreground/90 shadow-inner">
                    <span className="font-semibold text-primary mr-2">Overview:</span>
                    {data.summary}
                </div>

                {/* Chart Area */}
                <div className="h-[250px] w-full mt-2">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={data.metrics} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <defs>
                                <linearGradient id="colorSys" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorHr" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                            <XAxis
                                dataKey="date"
                                axisLine={false}
                                tickLine={false}
                                tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
                                dy={10}
                            />
                            <YAxis
                                axisLine={false}
                                tickLine={false}
                                tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
                            />
                            <Tooltip
                                contentStyle={{ borderRadius: '12px', border: '1px solid hsl(var(--border))', backgroundColor: 'hsl(var(--background))' }}
                            />
                            <Legend verticalAlign="top" height={36} iconType="circle" />
                            <Area
                                type="monotone"
                                dataKey="systolic_bp"
                                name="Systolic BP"
                                stroke="#ef4444"
                                strokeWidth={3}
                                fillOpacity={1}
                                fill="url(#colorSys)"
                                activeDot={{ r: 6, strokeWidth: 0 }}
                            />
                            <Area
                                type="monotone"
                                dataKey="heart_rate"
                                name="Heart Rate"
                                stroke="#3b82f6"
                                strokeWidth={3}
                                fillOpacity={1}
                                fill="url(#colorHr)"
                                activeDot={{ r: 6, strokeWidth: 0 }}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>

                {/* AI Actionable Tips */}
                {data.tips && data.tips.length > 0 && (
                    <div className="mt-2 space-y-3">
                        <h4 className="flex items-center gap-2 font-medium text-sm text-muted-foreground uppercase tracking-wider">
                            <Lightbulb className="w-4 h-4 text-amber-500" /> Actionable Recommendations
                        </h4>
                        <div className="grid grid-cols-1 gap-3">
                            {data.tips.map((tip, idx) => (
                                <div key={idx} className="flex items-start gap-3 bg-muted/30 p-3 rounded-lg border border-border/50">
                                    <div className="w-6 h-6 rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 flex items-center justify-center text-xs font-bold shrink-0">
                                        {idx + 1}
                                    </div>
                                    <p className="text-sm text-foreground/80 leading-snug pt-0.5">{tip}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
