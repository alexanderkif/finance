import { HttpClient } from '@angular/common/http';
import { Service, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import {
  AnalysisRequest,
  AnalysisResult,
  ExampleResponse,
  ParseResponse,
} from '../models/market-data';

@Service()
export class MarketApi {
  private readonly http = inject(HttpClient);

  getExample(symbol: string): Promise<ExampleResponse> {
    return firstValueFrom(
      this.http.get<ExampleResponse>(`/api/analysis/example/${encodeURIComponent(symbol)}`),
    );
  }

  parse(message: string, defaultSymbol: string): Promise<ParseResponse> {
    return firstValueFrom(
      this.http.post<ParseResponse>('/api/analysis/parse', {
        message,
        default_symbol: defaultSymbol,
      }),
    );
  }

  runAnalysis(request: AnalysisRequest): Promise<AnalysisResult> {
    return firstValueFrom(this.http.post<AnalysisResult>('/api/analysis/run', request));
  }
}
