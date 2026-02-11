const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export class ApiRequestError extends Error {
  status: number | null;
  path: string;
  details: string | null;

  constructor(message: string, status: number | null, path: string, details: string | null = null) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.path = path;
    this.details = details;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'GET',
      cache: 'no-store',
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'network error';
    throw new ApiRequestError(`Cannot reach backend API (${API_BASE})`, null, path, message);
  }

  if (!response.ok) {
    let details: string | null = null;
    try {
      const payload = await response.json();
      details =
        typeof payload?.detail === 'string'
          ? payload.detail
          : typeof payload?.message === 'string'
            ? payload.message
            : JSON.stringify(payload);
    } catch {
      try {
        details = await response.text();
      } catch {
        details = null;
      }
    }
    throw new ApiRequestError(`API request failed (${response.status})`, response.status, path, details);
  }

  return (await response.json()) as T;
}

export function readableApiError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === null) {
      return `Backend nicht erreichbar. Pruefe, ob die API unter ${API_BASE} laeuft.`;
    }
    if (error.details) {
      return `${error.message}: ${error.details}`;
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Unbekannter API-Fehler';
}
