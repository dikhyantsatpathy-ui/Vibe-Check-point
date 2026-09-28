// ============================================================================
// GoogleSignIn.tsx — authority sign-in gate. Google Identity Services renders
// its button here; the credential is exchanged for the HttpOnly session cookie
// by the backend (/api/admin/login). No identity data touches the frontend.
// ============================================================================

import { useEffect, useRef, useState } from "react";
import { googleLogin } from "../api";
import { useAuth, useToast } from "../app/state";

// The Google OAuth client ID must be supplied at build time via
// VITE_GOOGLE_CLIENT_ID. There used to be a hardcoded fallback here matching
// one in app/main.py. A client ID is not a secret, but a silent fallback
// means a misconfigured build signs in against an OAuth project nobody
// intended to authorise -- and the backend's allow-list is then evaluated
// against the wrong audience. Fail visibly instead.

/** True once the GSI client script (loaded in index.html) is ready. */
export function useGsiReady(): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (window.google?.accounts?.id) {
      setReady(true);
      return;
    }
    const timer = window.setInterval(() => {
      if (window.google?.accounts?.id) {
        setReady(true);
        window.clearInterval(timer);
      }
    }, 200);
    return () => window.clearInterval(timer);
  }, []);
  return ready;
}

export function GoogleSignInButton() {
  const containerRef = useRef<HTMLDivElement>(null);
  const ready = useGsiReady();
  const rendered = useRef(false);
  const { refresh } = useAuth();
  const { toast } = useToast();
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  useEffect(() => {
    if (!ready || !containerRef.current || rendered.current) return;
    rendered.current = true;
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
    if (!clientId) {
      console.error(
        "[SSB] VITE_GOOGLE_CLIENT_ID is not set. Google sign-in cannot initialise. " +
          "Copy frontend/.env.example to frontend/.env and set it, then rebuild.",
      );
      return;
    }
    window.google!.accounts!.id!.initialize({
      client_id: clientId,
      ux_mode: "popup",
      auto_prompt: false,
      callback: async (response) => {
        const res = await googleLogin(response.credential);
        if (res.ok) {
          toast("Officer session established.", "success");
          await refreshRef.current();
        } else {
          toast(res.error, "error");
        }
      },
    });
    window.google!.accounts!.id!.renderButton(containerRef.current, {
      theme: "outline",
      size: "large",
      text: "signin_with",
      shape: "rectangular",
    });
  }, [ready, toast]);

  return <div ref={containerRef} style={{ minHeight: 44, display: "inline-block" }} />;
}

export function SignInGate() {
  return (
    <div className="gate">
      <div className="gate__panel">
        <div className="gate__badge-top">Ministry of Home Affairs · Govt. of India</div>
        <h1 className="gate__title">Vibe check-point</h1>
        <p className="gate__sub">
          AI-based fake identity &amp; document screening · SIH 26188
          <br />
          Sashastra Seema Bal (Police II Division) · Secure operations desk
        </p>
        <div className="gate__hr" />

        {/* The previous "One-click access (SIH evaluator pass)" button called
            POST /api/admin/demo_login, which returned a super-admin session
            for a fixed address with no credentials. Removed. */}
        <div className="gate__options">
          <div className="gate__or"><span>sign in with an authorised Google account</span></div>
          <div style={{ display: "flex", justifyContent: "center" }}>
            <GoogleSignInButton />
          </div>
          <p className="gate__or gate__or--note">
            Access is granted by your administrator. Contact the duty super-admin
            if your account is not yet approved for a post and institution.
          </p>
        </div>

        <p className="gate__foot">
          Protected gov system · One traveller per session · No readable details stored
        </p>
      </div>
    </div>
  );
}