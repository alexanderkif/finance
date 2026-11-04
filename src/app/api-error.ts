import { HttpErrorResponse } from '@angular/common/http';

interface ApiErrorDetail {
  msg?: string;
}

interface ApiErrorBody {
  detail?: string | ApiErrorDetail[];
}

export function errorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    return readDetail(error.error) ?? fallbackMessage(error.status);
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Please try again in a moment.';
}

export function isRetryable(error: unknown): boolean {
  return (
    error instanceof HttpErrorResponse &&
    (error.status === 0 ||
      error.status === 408 ||
      error.status === 425 ||
      error.status === 502 ||
      error.status === 503 ||
      error.status === 504)
  );
}

function readDetail(body: unknown): string | null {
  if (typeof body === 'string' && body.trim().length > 0) {
    return body;
  }
  if (!body || typeof body !== 'object') {
    return null;
  }
  const detail = (body as ApiErrorBody).detail;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => item.msg)
      .filter((message): message is string => Boolean(message));
    return messages.length > 0 ? messages.join('; ') : null;
  }
  return null;
}

function fallbackMessage(status: number): string {
  switch (status) {
    case 0:
      return 'The analysis service could not be reached. Check the connection and try again.';
    case 429:
      return 'The free-tier service limit has been reached. Wait about a minute, then try again.';
    case 422:
      return 'The request could not be processed. Check the position details and try again.';
    case 502:
    case 503:
    case 504:
      return 'A market-data or AI service is temporarily unavailable. Please try again in about a minute.';
    default:
      return `The request failed (${status}). Please try again in a moment.`;
  }
}
