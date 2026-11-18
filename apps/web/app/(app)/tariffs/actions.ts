"use server";

import { api } from "@/lib/api/server";
import type { ProductDetail, TariffMatrix, TariffNews } from "@/lib/c6";

/** Server actions: the browser never calls the REST API itself (ADR-015). */
export async function loadProduct(hs6: string, market: string): Promise<{ data?: ProductDetail; error?: string }> {
  const client = await api();
  const { data } = await client.GET("/api/v1/tariffs/products/{hs6}", {
    params: { path: { hs6 }, query: { market: [market] } },
  });
  return data ? { data: data.data } : { error: "Could not load the product's tariff lines." };
}

/** Rates for a few origins of some products in some markets (the Route Planner and network cards). */
export async function loadRates(
  hs6s: string[],
  markets: string[],
  origins: string[],
): Promise<{ data?: TariffMatrix; meta?: { mode: string; sources?: string[]; as_of?: string; note?: string | null }; error?: string }> {
  const client = await api();
  const { data } = await client.GET("/api/v1/tariffs/matrix", {
    params: { query: { hs6: hs6s, market: markets, origin: origins } },
  });
  return data ? { data: data.data, meta: data.meta } : { error: "Could not load tariffs." };
}

/** One trade-policy event's tariff reading (the Disruption Radar card). */
export async function loadEventTariff(eventId: string): Promise<{ data?: TariffNews | null; error?: string }> {
  const client = await api();
  const { data } = await client.GET("/api/v1/tariffs/news", { params: { query: { event_id: eventId } } });
  return data ? { data: data.data[0] ?? null } : { error: "Could not load the tariff reading." };
}

/** Supplier Network drawer (T4): duty in the buyer's market on the products it orders. */
export async function loadNodeTariffs(
  skus: string[],
  market: string,
  origins: string[],
): Promise<{
  products?: { sku: string; hs6: string; name: string }[];
  data?: TariffMatrix;
  meta?: { mode: string; sources?: string[]; as_of?: string };
  error?: string;
}> {
  const client = await api();
  const overview = await client.GET("/api/v1/tariffs/overview");
  if (!overview.data) return { error: "Could not load tariffs." };
  // supply-graph SKUs carry the industry prefix ("G-TSHIRT"); the catalogue keys do not
  const keys = new Set(skus.map((s) => s.replace(/^[GP]-/, "")));
  const products = overview.data.data.products
    .filter((p) => p.key && keys.has(p.key))
    .map((p) => ({ sku: p.key as string, hs6: p.hs6, name: p.name }));
  if (!products.length) return { products: [] };
  const { data } = await client.GET("/api/v1/tariffs/matrix", {
    params: { query: { hs6: products.map((p) => p.hs6), market: [market], origin: origins } },
  });
  return data ? { products, data: data.data, meta: data.meta } : { error: "Could not load tariffs." };
}

const INDUSTRY_HS6: Record<string, string[]> = { garments: ["610910", "620342"], pharma: ["300490"] };
const WATCHED_MARKETS = ["USA", "GBR", "EUN", "JPN", "CAN"];
const WATCHED_ORIGINS = ["BGD", "VNM", "KHM", "IND", "CHN", "PAK", "LKA"];

/** Disruption Radar (T5): what a trade-policy story says, and what the schedule says today. */
export async function loadTariffCheck(eventId: string): Promise<{
  news?: TariffNews | null;
  data?: TariffMatrix;
  meta?: { mode: string; sources?: string[]; as_of?: string };
  scope?: { hs6: string[]; markets: string[]; origins: string[] };
  error?: string;
}> {
  const client = await api();
  const res = await client.GET("/api/v1/tariffs/news", { params: { query: { event_id: eventId } } });
  if (!res.data) return { error: "Could not load the tariff reading." };
  const news = res.data.data[0] ?? null;
  const hs6 = [...new Set((news?.industries.length ? news.industries : ["garments"]).flatMap((i) => INDUSTRY_HS6[i] ?? []))];
  const markets = news?.markets.filter((m) => WATCHED_MARKETS.includes(m)) ?? [];
  const origins = news?.origins.filter((o) => WATCHED_ORIGINS.includes(o)) ?? [];
  const scope = { hs6, markets: markets.length ? markets : ["USA", "GBR", "EUN"], origins: origins.length ? origins : ["BGD"] };
  const { data } = await client.GET("/api/v1/tariffs/matrix", {
    params: { query: { hs6: scope.hs6, market: scope.markets, origin: scope.origins } },
  });
  return data ? { news, data: data.data, meta: data.meta, scope } : { news, error: "Could not load tariffs." };
}
