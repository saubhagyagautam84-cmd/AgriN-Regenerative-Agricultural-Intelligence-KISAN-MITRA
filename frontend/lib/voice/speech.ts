/**
 * Shared speech-synthesis (text-to-speech) and speech-recognition
 * (voice-to-text) helpers - used by the wizard's per-question voice-read
 * buttons and by the chat/voice bot (components/ChatBotWidget.tsx).
 *
 * Both Web Speech APIs have inconsistent browser support (recognition
 * especially - reliable only in Chrome-based browsers), so every entry
 * point here fails silently rather than breaking the page, per this
 * project's established pattern (see FarmInputForm's original voice-read
 * button).
 */

import type { LanguageCode } from "@/lib/i18n/languages";

/** speechSynthesis / SpeechRecognition BCP-47 language tags - IN-region variants where available. */
export const SPEECH_LANG: Record<LanguageCode, string> = {
  en: "en-IN",
  hi: "hi-IN",
  pa: "pa-IN",
  mr: "mr-IN",
  gu: "gu-IN",
  bn: "bn-IN",
  ta: "ta-IN",
  te: "te-IN",
  kn: "kn-IN",
};

/** Best-effort only - speech synthesis support is inconsistent across browsers/devices. */
export function speak(text: string, lang: LanguageCode) {
  try {
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = SPEECH_LANG[lang] ?? "en-IN";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  } catch {
    // no-op
  }
}

export function stopSpeaking() {
  try {
    window.speechSynthesis.cancel();
  } catch {
    // no-op
  }
}

/** True only when the browser exposes a usable SpeechRecognition constructor. */
export function isSpeechRecognitionSupported(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

interface RecognitionHandle {
  stop: () => void;
}

/**
 * Starts one voice-input session. Calls `onResult` with the final
 * transcript, or `onError` if recognition fails/isn't supported (e.g. no
 * microphone permission, unsupported browser) - never throws.
 * Returns a handle to stop listening early, or null if it couldn't start.
 */
export function startListening(
  lang: LanguageCode,
  onResult: (transcript: string) => void,
  onEnd: () => void,
  onError?: (reason: string) => void,
): RecognitionHandle | null {
  try {
    const w = window as unknown as Record<string, unknown>;
    const Recognition = (w.SpeechRecognition || w.webkitSpeechRecognition) as
      | (new () => SpeechRecognitionLike)
      | undefined;
    if (!Recognition) {
      onError?.("unsupported");
      return null;
    }
    const recognition = new Recognition();
    recognition.lang = SPEECH_LANG[lang] ?? "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript ?? "";
      if (transcript) onResult(transcript);
    };
    recognition.onerror = () => onError?.("recognition-error");
    recognition.onend = () => onEnd();

    recognition.start();
    return { stop: () => recognition.stop() };
  } catch {
    onError?.("exception");
    return null;
  }
}

// Minimal shape of the Web Speech API's SpeechRecognition - not in
// TypeScript's default DOM lib, so declared narrowly here rather than
// pulling in a whole @types/dom-speech-recognition dependency.
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  onresult: ((event: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onend: (() => void) | null;
}
