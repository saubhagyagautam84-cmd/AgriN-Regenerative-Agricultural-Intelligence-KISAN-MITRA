import type { LanguageCode } from "../languages";
import en from "./en";
import hi from "./hi";
import pa from "./pa";
import mr from "./mr";
import gu from "./gu";
import bn from "./bn";
import ta from "./ta";
import te from "./te";
import kn from "./kn";
import type { TranslationShape } from "./en";

export const TRANSLATIONS: Record<LanguageCode, TranslationShape> = {
  en,
  hi,
  pa,
  mr,
  gu,
  bn,
  ta,
  te,
  kn,
};

export type { TranslationShape };
