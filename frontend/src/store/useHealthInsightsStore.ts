import { create } from 'zustand';

interface MetricData {
    date: string;
    [key: string]: string | number | null | undefined;
}

interface HealthProfile {
    weight?: string | null;
    height?: string | null;
    age?: string | null;
    blood_group?: string | null;
    allergies?: string[] | null;
}

interface HealthData {
    summary: string;
    profile?: HealthProfile;
    available_metrics?: string[];
    metrics: MetricData[];
    tips: string[];
}

interface HealthInsightsState {
    data: HealthData | null;
    setData: (data: HealthData | null) => void;
    loading: boolean;
    setLoading: (loading: boolean) => void;
    error: string | null;
    setError: (error: string | null) => void;
    hasLoaded: boolean;
    setHasLoaded: (hasLoaded: boolean) => void;
}

export const useHealthInsightsStore = create<HealthInsightsState>((set) => ({
    data: null,
    setData: (data) => set({ data }),
    loading: false,
    setLoading: (loading) => set({ loading }),
    error: null,
    setError: (error) => set({ error }),
    hasLoaded: false,
    setHasLoaded: (hasLoaded) => set({ hasLoaded }),
}));
