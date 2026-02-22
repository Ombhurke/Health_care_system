import { useCallback, useEffect, useRef, useState } from "react";
import type { User } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { useNavigate } from "react-router-dom";

export interface Profile {
  id: string;
  role: "patient" | "doctor" | "hospital";
  full_name: string;
  phone: string;
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const navigate = useNavigate();

  // Prevent state updates after unmount + avoid duplicate fetches
  const mountedRef = useRef(true);
  const lastFetchedUserIdRef = useRef<string | null>(null);

  const fetchProfile = useCallback(async (userId: string) => {
    try {
      // Avoid spamming the same request repeatedly
      if (lastFetchedUserIdRef.current === userId && profile) return;

      const { data, error } = await supabase
        .from("profiles")
        .select("*")
        .eq("id", userId)
        .maybeSingle(); // ✅ IMPORTANT: no error when 0 rows (fixes PGRST116 spam) [file:482]

      if (error) throw error;

      if (!mountedRef.current) return;
      setProfile((data as Profile) ?? null);
      lastFetchedUserIdRef.current = userId;
    } catch (err) {
      // If profile row doesn't exist yet (or RLS blocks), don't spam errors endlessly.
      // Keep profile null and let UI decide what to show.
      console.error("Error fetching profile:", err);
      if (!mountedRef.current) return;
      setProfile(null);
    } finally {
      if (!mountedRef.current) return;
      setLoading(false);
    }
  }, [profile]);

  useEffect(() => {
    mountedRef.current = true;

    // Initial session load
    supabase.auth
      .getSession()
      .then(({ data: { session }, error }) => {
        if (error) throw error;

        const nextUser = session?.user ?? null;
        if (!mountedRef.current) return;

        setUser(nextUser);

        if (nextUser) {
          // keep loading true until profile resolution finishes
          setLoading(true);
          fetchProfile(nextUser.id);
        } else {
          setProfile(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error("Error getting session:", err);
        if (!mountedRef.current) return;
        setUser(null);
        setProfile(null);
        setLoading(false);
      });

    // Auth change listener
    const { data: authListener } = supabase.auth.onAuthStateChange((_event, session) => {
      const nextUser = session?.user ?? null;

      if (!mountedRef.current) return;
      setUser(nextUser);

      if (nextUser) {
        setLoading(true);
        fetchProfile(nextUser.id);
      } else {
        lastFetchedUserIdRef.current = null;
        setProfile(null);
        setLoading(false);
      }
    });

    return () => {
      mountedRef.current = false;
      authListener.subscription.unsubscribe();
    };
  }, [fetchProfile]);

  const signOut = useCallback(async () => {
    try {
      await supabase.auth.signOut();
    } finally {
      // Always route to login even if signOut throws
      navigate("/login");
    }
  }, [navigate]);

  return {
    user,
    profile,
    loading,
    signOut,
    isAuthenticated: !!user,
    role: profile?.role ?? null,
  };
}
