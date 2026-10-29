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
  return status === 0 ? 'The API could not be reached.' : `Request failed (${status})`;
}
