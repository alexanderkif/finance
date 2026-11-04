import { HttpClient } from '@angular/common/http';
import { Service, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import {
  AnalysisRequest,
  AnalysisResult,
  ExampleResponse,
  ParseResponse,
} from '../models/market-data';

export function requestAbortedError(): DOMException {
  return new DOMException('The request was cancelled.', 'AbortError');
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

@Service()
export class MarketApi {
  private readonly http = inject(HttpClient);

  getExample(symbol: string, signal?: AbortSignal): Promise<ExampleResponse> {
    return this.send(
      this.http.get<ExampleResponse>(`/api/analysis/example/${encodeURIComponent(symbol)}`),
      signal,
    );
  }

  parse(message: string, defaultSymbol: string, signal?: AbortSignal): Promise<ParseResponse> {
    return this.send(
      this.http.post<ParseResponse>('/api/analysis/parse', {
        message,
        default_symbol: defaultSymbol,
      }),
      signal,
    );
  }

  runAnalysis(request: AnalysisRequest, signal?: AbortSignal): Promise<AnalysisResult> {
    return this.send(this.http.post<AnalysisResult>('/api/analysis/run', request), signal);
  }

  private send<T>(request: Observable<T>, signal?: AbortSignal): Promise<T> {
    if (!signal) {
      return firstValueFrom(request);
    }
    if (signal.aborted) {
      return Promise.reject(requestAbortedError());
    }
    return new Promise<T>((resolve, reject) => {
      const subscription = request.subscribe({ next: resolve, error: reject });
      const onAbort = (): void => {
        subscription.unsubscribe();
        reject(requestAbortedError());
      };
      signal.addEventListener('abort', onAbort, { once: true });
      subscription.add(() => signal.removeEventListener('abort', onAbort));
    });
  }
}
