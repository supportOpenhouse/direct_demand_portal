/**
 * Thin typed fetch wrapper for the /v1 API.
 * - Base URL: VITE_API_URL + '/v1'
 * - Attaches `Authorization: Bearer <token>` from localStorage('dd_token')
 * - Non-2xx responses throw ApiError carrying the contract error envelope
 *   { detail, fields? }.
 */

export const TOKEN_KEY = 'dd_token';
export const USER_KEY = 'dd_user';

const BASE = `${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/v1`;

export class ApiError extends Error {
  status: number;
  detail: string;
  fields?: Record<string, string>;

  constructor(status: number, detail: string, fields?: Record<string, string>) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.fields = fields;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'Network error — is the API running?');
  }

  let data: unknown = null;
  if (res.status !== 204) {
    try {
      data = await res.json();
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    const env = (data ?? {}) as { detail?: unknown; fields?: Record<string, string> };
    const detail = typeof env.detail === 'string' ? env.detail : res.statusText || 'Request failed';
    throw new ApiError(res.status, detail, env.fields);
  }

  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
};
