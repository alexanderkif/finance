import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Service, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import {
  AnalysisPosition,
  AnalysisRequest,
  AnalysisResult,
  AnalysisStreamEvent,
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

  parse(
    message: string,
    defaultSymbol: string,
    signal?: AbortSignal,
    context: AnalysisPosition[] = [],
  ): Promise<ParseResponse> {
    return this.send(
      this.http.post<ParseResponse>('/api/analysis/parse', {
        message,
        default_symbol: defaultSymbol,
        context,
      }),
      signal,
    );
  }

  async streamAnalysis(
    request: AnalysisRequest,
    onEvent: (event: AnalysisStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<AnalysisResult> {
    let response: Response;
    try {
      response = await fetch('/api/analysis/run/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/x-ndjson',
        },
        body: JSON.stringify(request),
        signal,
      });
    } catch (error) {
      if (signal?.aborted || isAbortError(error)) {
        throw error;
      }
      throw new HttpErrorResponse({
        status: 0,
        error: {
          detail: 'The analysis service could not be reached. Check the connection and try again.',
        },
      });
    }
    if (!response.ok) {
      throw new HttpErrorResponse({
        status: response.status,
        error: { detail: await this.readErrorDetail(response) },
      });
    }
    if (!response.body) {
      throw new HttpErrorResponse({
        status: 502,
        error: { detail: 'The analysis stream is unavailable.' },
      });
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let result: AnalysisResult | null = null;
    try {
      for (;;) {
        const chunk = await reader.read();
        if (chunk.done) {
          break;
        }
        buffer += decoder.decode(chunk.value, { stream: true });
        let newline = buffer.indexOf('\n');
        while (newline >= 0) {
          const line = buffer.slice(0, newline).trim();
          buffer = buffer.slice(newline + 1);
          if (line) {
            result = this.handleStreamLine(line, onEvent) ?? result;
          }
          newline = buffer.indexOf('\n');
        }
      }
      buffer += decoder.decode();
      const remaining = buffer.trim();
      if (remaining) {
        result = this.handleStreamLine(remaining, onEvent) ?? result;
      }
    } catch (error) {
      if (error instanceof HttpErrorResponse || signal?.aborted || isAbortError(error)) {
        throw error;
      }
      throw new HttpErrorResponse({
        status: 0,
        error: {
          detail: 'The analysis connection was interrupted. Check the connection and try again.',
        },
      });
    } finally {
      reader.releaseLock();
    }

    if (!result) {
      throw new HttpErrorResponse({
        status: 502,
        error: { detail: 'The analysis stream ended before a result was available.' },
      });
    }
    return result;
  }

  private handleStreamLine(
    line: string,
    onEvent: (event: AnalysisStreamEvent) => void,
  ): AnalysisResult | null {
    const event = JSON.parse(line) as AnalysisStreamEvent;
    onEvent(event);
    if (event.type === 'error') {
      throw new HttpErrorResponse({
        status: event.status,
        error: { detail: event.detail },
      });
    }
    return event.type === 'result' ? event.result : null;
  }

  private async readErrorDetail(response: Response): Promise<string> {
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') {
        return body.detail;
      }
    } catch {
      // Fall through to the status-based message.
    }
    return `The analysis service returned HTTP ${response.status}.`;
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
