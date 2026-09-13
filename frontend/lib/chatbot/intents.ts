/**
 * Rule-based FAQ matching for the chat/voice bot (components/ChatBotWidget.tsx).
 *
 * Deliberately NOT an LLM - see the design decision this was built against:
 * scripted, instant, free, always on-brand, never fabricates farm advice.
 * Its only job is to explain what the app does and point the user at the
 * real feature - it never answers an actual soil/water/crop question with
 * invented numbers.
 *
 * Keyword lists are hand-written, not native-speaker reviewed, same
 * documented limitation as the rest of this project's translations (see
 * lib/i18n/languages.ts) - English keywords are always checked in addition
 * to the active language's, since many users type in English regardless of
 * the UI language.
 */

import type { LanguageCode } from "@/lib/i18n/languages";

export type IntentId =
  | "greeting"
  | "identity"
  | "capabilities"
  | "howToStart"
  | "soil"
  | "water"
  | "cropRecommendation"
  | "rotation"
  | "regenScore"
  | "photoCheck"
  | "language"
  | "darkMode"
  | "login"
  | "familyMember"
  | "contact"
  | "myReport";

export type ResolvedIntentId = IntentId | "fallback";

interface Intent {
  id: IntentId;
  keywords: Partial<Record<LanguageCode, string[]>>;
}

// Order matters: conversational intents are checked before domain keywords,
// so "who are you and what can you help with" resolves to identity, not a
// coincidental domain-word match.
const INTENTS: Intent[] = [
  {
    id: "greeting",
    keywords: {
      en: ["hi", "hii", "hello", "hey", "namaste"],
      hi: ["नमस्ते", "हैलो", "हाय"],
      pa: ["ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "ਹੈਲੋ"],
      mr: ["नमस्कार", "हॅलो"],
      gu: ["નમસ્તે", "હેલો"],
      bn: ["নমস্কার", "হ্যালো"],
      ta: ["வணக்கம்"],
      te: ["నమస్కారం"],
      kn: ["ನಮಸ್ಕಾರ"],
    },
  },
  {
    id: "identity",
    keywords: {
      en: ["who are you", "what are you", "your name"],
      hi: ["तुम कौन हो", "आप कौन हैं"],
      pa: ["ਤੁਸੀਂ ਕੌਣ ਹੋ"],
      mr: ["तू कोण आहेस", "तुम्ही कोण आहात"],
      gu: ["તમે કોણ છો"],
      bn: ["তুমি কে", "আপনি কে"],
      ta: ["நீ யார்", "நீங்கள் யார்"],
      te: ["నువ్వు ఎవరు", "మీరు ఎవరు"],
      kn: ["ನೀನು ಯಾರು", "ನೀವು ಯಾರು"],
    },
  },
  {
    id: "capabilities",
    keywords: {
      en: ["what can you do", "what do you do", "help"],
      hi: ["तुम क्या करते हो", "मदद"],
      pa: ["ਤੁਸੀਂ ਕੀ ਕਰਦੇ ਹੋ", "ਮਦਦ"],
      mr: ["तू काय करतोस", "मदत"],
      gu: ["તમે શું કરો છો", "મદદ"],
      bn: ["তুমি কী করো", "সাহায্য"],
      ta: ["நீ என்ன செய்கிறாய்", "உதவி"],
      te: ["నువ్వు ఏమి చేస్తావు", "సహాయం"],
      kn: ["ನೀನು ಏನು ಮಾಡುತ್ತೀಯ", "ಸಹಾಯ"],
    },
  },
  {
    id: "howToStart",
    keywords: {
      en: ["how do i start", "how does this work", "how to use"],
      hi: ["कैसे शुरू करें", "यह कैसे काम करता है"],
      pa: ["ਕਿਵੇਂ ਸ਼ੁਰੂ ਕਰਾਂ"],
      mr: ["कसे सुरू करावे"],
      gu: ["કેવી રીતે શરૂ કરવું"],
      bn: ["কীভাবে শুরু করব"],
      ta: ["எப்படி தொடங்குவது"],
      te: ["ఎలా ప్రారంభించాలి"],
      kn: ["ಹೇಗೆ ಪ್ರಾರಂಭಿಸುವುದು"],
    },
  },
  {
    id: "soil",
    keywords: {
      en: ["soil"],
      hi: ["मिट्टी"],
      pa: ["ਮਿੱਟੀ"],
      mr: ["माती"],
      gu: ["માટી"],
      bn: ["মাটি"],
      ta: ["மண்"],
      te: ["మట్టి"],
      kn: ["ಮಣ್ಣು"],
    },
  },
  {
    id: "water",
    keywords: {
      en: ["water", "irrigation", "irrigate"],
      hi: ["पानी", "सिंचाई"],
      pa: ["ਪਾਣੀ", "ਸਿੰਚਾਈ"],
      mr: ["पाणी", "सिंचन"],
      gu: ["પાણી", "સિંચાઈ"],
      bn: ["জল", "পানি", "সেচ"],
      ta: ["நீர்", "பாசனம்"],
      te: ["నీరు", "నీటిపారుదల"],
      kn: ["ನೀರು", "ನೀರಾವರಿ"],
    },
  },
  {
    id: "cropRecommendation",
    keywords: {
      en: ["what to grow", "crop recommendation", "which crop"],
      hi: ["क्या उगाएं", "फसल सुझाव"],
      pa: ["ਕੀ ਬੀਜੀਏ"],
      mr: ["काय पिकवावे"],
      gu: ["શું ઉગાડવું"],
      bn: ["কী চাষ করব"],
      ta: ["என்ன பயிரிடுவது"],
      te: ["ఏమి పండించాలి"],
      kn: ["ಏನು ಬೆಳೆಯಬೇಕು"],
    },
  },
  {
    id: "rotation",
    keywords: {
      en: ["rotation"],
      hi: ["फसल चक्र"],
      pa: ["ਫ਼ਸਲ ਚੱਕਰ"],
      mr: ["पीक फेरपालट", "फेरपालट"],
      gu: ["પાક ચક્ર"],
      bn: ["ফসল আবর্তন"],
      ta: ["பயிர் சுழற்சி"],
      te: ["పంట మార్పిడి"],
      kn: ["ಬೆಳೆ ಸರದಿ"],
    },
  },
  {
    id: "regenScore",
    keywords: {
      en: ["regeneration score", "regen score"],
      hi: ["पुनर्जनन स्कोर"],
      pa: ["ਪੁਨਰ-ਸਿਰਜਣ ਸਕੋਰ"],
      mr: ["पुनर्निर्मिती स्कोअर"],
      gu: ["પુનર્જનન સ્કોર"],
      bn: ["পুনর্জন্ম স্কোর"],
      ta: ["மறுஉருவாக்க மதிப்பெண்"],
      te: ["పునరుత్పత్తి స్కోరు"],
      kn: ["ಪುನರುತ್ಪಾದನಾ ಸ್ಕೋರ್"],
    },
  },
  {
    id: "photoCheck",
    keywords: {
      en: ["photo", "disease"],
      hi: ["फोटो", "बीमारी"],
      pa: ["ਫੋਟੋ", "ਬਿਮਾਰੀ"],
      mr: ["फोटो", "रोग"],
      gu: ["ફોટો", "રોગ"],
      bn: ["ছবি", "রোগ"],
      ta: ["புகைப்படம்", "நோய்"],
      te: ["ఫోటో", "వ్యాధి"],
      kn: ["ಫೋಟೋ", "ರೋಗ"],
    },
  },
  {
    id: "language",
    keywords: {
      en: ["language"],
      hi: ["भाषा"],
      pa: ["ਭਾਸ਼ਾ"],
      mr: ["भाषा"],
      gu: ["ભાષા"],
      bn: ["ভাষা"],
      ta: ["மொழி"],
      te: ["భాష"],
      kn: ["ಭಾಷೆ"],
    },
  },
  {
    id: "darkMode",
    keywords: {
      en: ["dark mode", "night mode", "theme"],
      hi: ["डार्क मोड", "रात मोड"],
      pa: ["ਰਾਤ ਮੋਡ"],
      mr: ["रात्र मोड", "डार्क मोड"],
      gu: ["રાત મોડ"],
      bn: ["রাত মোড", "ডার্ক মোড"],
      ta: ["இரவு பயன்முறை"],
      te: ["రాత్రి మోడ్"],
      kn: ["ರಾತ್ರಿ ಮೋಡ್"],
    },
  },
  {
    id: "login",
    keywords: {
      en: ["login", "sign in", "log in"],
      hi: ["लॉगिन"],
      pa: ["ਲੌਗਇਨ"],
      mr: ["लॉगिन"],
      gu: ["લૉગિન"],
      bn: ["লগইন"],
      ta: ["உள்நுழை"],
      te: ["లాగిన్"],
      kn: ["ಲಾಗಿನ್"],
    },
  },
  {
    id: "familyMember",
    keywords: {
      en: ["family member", "family"],
      hi: ["परिवार"],
      pa: ["ਪਰਿਵਾਰ"],
      mr: ["कुटुंब"],
      gu: ["કુટુંબ"],
      bn: ["পরিবার"],
      ta: ["குடும்பம்"],
      te: ["కుటుంబం"],
      kn: ["ಕುಟುಂಬ"],
    },
  },
  {
    id: "contact",
    keywords: {
      en: ["contact"],
      hi: ["संपर्क"],
      pa: ["ਸੰਪਰਕ"],
      mr: ["संपर्क"],
      gu: ["સંપર્ક"],
      bn: ["যোগাযোগ"],
      ta: ["தொடர்பு"],
      te: ["సంప్రదించండి", "సంప్రదింపు"],
      kn: ["ಸಂಪರ್ಕ"],
    },
  },
  {
    id: "myReport",
    keywords: {
      en: ["my report", "report"],
      hi: ["रिपोर्ट"],
      pa: ["ਰਿਪੋਰਟ"],
      mr: ["अहवाल", "रिपोर्ट"],
      gu: ["રિપોર્ટ"],
      bn: ["রিপোর্ট"],
      ta: ["அறிக்கை"],
      te: ["నివేదిక"],
      kn: ["ವರದಿ"],
    },
  },
];

function tokenize(input: string): string[] {
  return input.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

/** Whole-word match for short keywords (avoids "hi" matching inside "history"); substring match for longer phrases. */
function keywordMatches(normalizedInput: string, words: string[], keyword: string): boolean {
  const kw = keyword.toLowerCase();
  if (kw.length <= 3 && !kw.includes(" ")) {
    return words.includes(kw);
  }
  return normalizedInput.includes(kw);
}

export function matchIntent(input: string, lang: LanguageCode): ResolvedIntentId {
  const normalized = input.trim().toLowerCase();
  if (!normalized) return "fallback";
  const words = tokenize(normalized);

  for (const intent of INTENTS) {
    const activeLangKeywords = lang === "en" ? [] : (intent.keywords[lang] ?? []);
    const englishKeywords = intent.keywords.en ?? [];
    const candidates = [...activeLangKeywords, ...englishKeywords];
    if (candidates.some((kw) => keywordMatches(normalized, words, kw))) {
      return intent.id;
    }
  }
  return "fallback";
}
