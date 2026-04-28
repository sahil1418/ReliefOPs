"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { ConfirmationResult } from "firebase/auth";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { confirmPhoneSignIn, startPhoneSignIn } from "@/lib/auth";

const RECAPTCHA_CONTAINER = "recaptcha-container";

export default function PhoneLoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const dest = searchParams.get("from") ?? "/dashboard";

  const [phase, setPhase] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("+1");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirmationRef = useRef<ConfirmationResult | null>(null);

  // Best-effort cleanup of the invisible reCAPTCHA on unmount.
  useEffect(() => () => {
    const el = document.getElementById(RECAPTCHA_CONTAINER);
    if (el) el.innerHTML = "";
  }, []);

  async function handleSendCode(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!/^\+\d{8,15}$/.test(phone)) {
      setError("Phone must be E.164, e.g. +8801712345678");
      return;
    }
    setSubmitting(true);
    try {
      const confirmation = await startPhoneSignIn(phone, RECAPTCHA_CONTAINER);
      confirmationRef.current = confirmation;
      setPhase("code");
    } catch (err) {
      setError((err instanceof Error ? err.message : "Failed to send code").replace("Firebase: ", ""));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerifyCode(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!confirmationRef.current) {
      setError("No confirmation in flight. Restart the OTP flow.");
      setPhase("phone");
      return;
    }
    if (!/^\d{4,8}$/.test(code)) {
      setError("Code must be 4-8 digits.");
      return;
    }
    setSubmitting(true);
    try {
      await confirmPhoneSignIn(confirmationRef.current, code);
      router.replace(dest);
    } catch (err) {
      setError((err instanceof Error ? err.message : "Invalid code").replace("Firebase: ", ""));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">Sign in by phone</CardTitle>
        <CardDescription>
          {phase === "phone"
            ? "Enter your phone number in international format (E.164). Best for field volunteers on low connectivity."
            : `We sent a 6-digit code to ${phone}. Check the auth emulator UI at http://127.0.0.1:4000/auth.`}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {phase === "phone" ? (
          <form onSubmit={handleSendCode} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="phone">Phone (E.164)</Label>
              <Input
                id="phone"
                type="tel"
                inputMode="tel"
                placeholder="+8801712345678"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={submitting}
                required
              />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Sending…" : "Send code"}
            </Button>
          </form>
        ) : (
          <form onSubmit={handleVerifyCode} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="code">Verification code</Label>
              <Input
                id="code"
                inputMode="numeric"
                pattern="[0-9]*"
                placeholder="123456"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                disabled={submitting}
                autoFocus
                required
              />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Verifying…" : "Verify & sign in"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => {
                setPhase("phone");
                setCode("");
                confirmationRef.current = null;
              }}
            >
              Use a different number
            </Button>
          </form>
        )}

        <div id={RECAPTCHA_CONTAINER} />
      </CardContent>

      <CardFooter className="justify-center text-xs text-muted-foreground">
        <Link className="underline" href="/login">
          ← Back to email sign-in
        </Link>
      </CardFooter>
    </Card>
  );
}
