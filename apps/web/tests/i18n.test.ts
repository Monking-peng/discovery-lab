import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE_NAME,
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  getInitialLocale,
  isLocale,
  isMessageKey,
  messages,
  normalizeLocale,
  parseLocaleCookie,
  serializeLocaleCookie,
  serializeLocaleForStorage,
  translate,
} from "../lib/i18n";

describe("locale normalization and selection", () => {
  it.each([
    ["en", "en"],
    [" EN-us ", "en"],
    ["en_GB", "en"],
    ["zh", "zh-CN"],
    ["zh_CN", "zh-CN"],
    ["zh-Hans", "zh-CN"],
    ["zh-Hans-SG", "zh-CN"],
    ["zh-SG", "zh-CN"],
  ] as const)("normalizes %s to %s", (input, expected) => {
    expect(normalizeLocale(input)).toBe(expected);
  });

  it.each([null, undefined, 123, "", "fr", "zh-TW", "zh-Hant"])(
    "rejects unsupported locale %s",
    (input) => {
      expect(normalizeLocale(input)).toBeNull();
    },
  );

  it("uses the first supported candidate and otherwise defaults to English", () => {
    expect(getInitialLocale("fr-FR", "zh-Hans-CN", "en-US")).toBe("zh-CN");
    expect(getInitialLocale(undefined, "fr-FR")).toBe(DEFAULT_LOCALE);
  });

  it("keeps the supported-locale runtime guard narrow", () => {
    expect(SUPPORTED_LOCALES).toEqual(["en", "zh-CN"]);
    expect(isLocale("en")).toBe(true);
    expect(isLocale("zh-CN")).toBe(true);
    expect(isLocale("zh-cn")).toBe(false);
    expect(isLocale(null)).toBe(false);
  });
});

describe("message catalog and interpolation", () => {
  it("provides exactly the same keys in both locales", () => {
    expect(Object.keys(messages["zh-CN"]).sort()).toEqual(Object.keys(messages.en).sort());
  });

  it("returns the expected English and Simplified Chinese product labels", () => {
    expect(translate("en", "nav.evidence")).toBe("Evidence Explorer");
    expect(translate("zh-CN", "nav.evidence")).toBe("证据浏览器");
    expect(translate("en", "language.zh")).toBe("简体中文");
    expect(translate("zh-CN", "language.zh")).toBe("简体中文");
  });

  it("interpolates every supplied variable without changing the catalog", () => {
    expect(translate("en", "evidence.count", { visible: 2, total: 7 })).toBe("2 of 7");
    expect(translate("zh-CN", "evidence.count", { visible: 2, total: 7 })).toBe(
      "显示 2 / 共 7",
    );
    expect(messages.en["evidence.count"]).toBe("{visible} of {total}");
  });

  it("leaves missing interpolation tokens visible for diagnosis", () => {
    expect(translate("en", "demo.body", { url: "http://localhost:8010" })).toContain(
      "{error}",
    );
  });

  it("recognizes only real message keys", () => {
    expect(isMessageKey("claims.previewBadge")).toBe(true);
    expect(isMessageKey("claims.not-a-real-key")).toBe(false);
  });
});

describe("locale persistence helpers", () => {
  it("reads the locale cookie regardless of surrounding cookies", () => {
    expect(parseLocaleCookie("session=abc; discovery_lab_locale=zh-CN; theme=dark")).toBe(
      "zh-CN",
    );
    expect(parseLocaleCookie("discovery_lab_locale=en%2DUS")).toBe("en");
  });

  it("returns null for a missing or unsupported locale cookie", () => {
    expect(parseLocaleCookie("session=abc")).toBeNull();
    expect(parseLocaleCookie("discovery_lab_locale=fr-FR")).toBeNull();
  });

  it("serializes stable storage and one-year same-site cookie values", () => {
    expect(LOCALE_STORAGE_KEY).toBe("discovery-lab.locale");
    expect(LOCALE_COOKIE_NAME).toBe("discovery_lab_locale");
    expect(serializeLocaleForStorage("zh-CN")).toBe("zh-CN");
    expect(serializeLocaleCookie("zh-CN")).toBe(
      "discovery_lab_locale=zh-CN; Path=/; Max-Age=31536000; SameSite=Lax",
    );
  });
});
