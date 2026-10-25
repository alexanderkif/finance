import { Service } from '@angular/core';
import {
  CandlesResponse,
  ChartRange,
  InsightsResponse,
  SearchResponse,
} from '../models/market-data';

@Service()
export class MarketData {
  getCandles(ticker: string, range: ChartRange, signal: AbortSignal): Promise<CandlesResponse> {
    return this.get(
      `/api/candles/${encodeURIComponent(ticker)}?range=${range}&interval=1d`,
      signal,
    );
  }

  getInsights(ticker: string, signal: AbortSignal): Promise<InsightsResponse> {
    return this.get(`/api/insights/${encodeURIComponent(ticker)}`, signal);
  }

  search(query: string, signal: AbortSignal): Promise<SearchResponse> {
    return this.get(`/api/search?q=${encodeURIComponent(query)}`, signal);
  }

  private async get<T>(url: string, signal: AbortSignal): Promise<T> {
    const response = await fetch(url, { signal });

    if (!response.ok) {
      const error = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(error?.detail ?? `Request failed (${response.status})`);
    }

    return (await response.json()) as T;
  }
}
