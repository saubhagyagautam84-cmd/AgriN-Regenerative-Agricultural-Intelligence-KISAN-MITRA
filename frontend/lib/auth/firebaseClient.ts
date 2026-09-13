/**
 * Firebase client SDK setup for phone-number OTP login.
 *
 * Reads its config from NEXT_PUBLIC_FIREBASE_* env vars (see
 * .env.local.example) - none of these are secrets (Firebase web config is
 * meant to be public; the project's security rules do the real gating), but
 * until they're set this app has no way to send a real OTP. `isFirebaseConfigured()`
 * lets the UI say so plainly instead of throwing a raw SDK error.
 *
 * To get these values: console.firebase.google.com -> your project ->
 * Project settings -> General -> "Your apps" -> Web app -> SDK setup and
 * configuration. Also enable Build -> Authentication -> Sign-in method ->
 * Phone.
 */
import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

export function isFirebaseConfigured(): boolean {
  return Boolean(firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId);
}

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

export function getFirebaseAuth(): Auth {
  if (!isFirebaseConfigured()) {
    throw new Error("firebase-not-configured");
  }
  if (!app) {
    app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
  }
  if (!auth) {
    auth = getAuth(app);
  }
  return auth;
}
