const configuredApiUrl =
  process.env.NEXT_PUBLIC_DEVICEOPS_API_URL ?? "http://127.0.0.1:8000";

export const API_BASE_URL = configuredApiUrl.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ApiRequestOptions {
  signal?: AbortSignal;
  token?: string;
  onUnauthorized?: () => void;
}

function requestHeaders(token?: string, hasJsonBody = false): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (hasJsonBody) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function responseError(response: Response): Promise<ApiError> {
  let detail = `The API returned HTTP ${response.status}.`;
  try {
    const body = (await response.json()) as {
      detail?: string | Array<{ msg?: string }>;
    };
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((item) => item.msg)
        .filter((message): message is string => Boolean(message));
      if (messages.length > 0) detail = messages.join("; ");
    }
  } catch {
    // The status code is sufficient when the response is not JSON.
  }
  return new ApiError(detail, response.status);
}

export async function apiGet<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      cache: "no-store",
      headers: requestHeaders(options.token),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      `Cannot reach the DeviceOps API at ${API_BASE_URL}.`,
      null,
    );
  }

  if (!response.ok) {
    const error = await responseError(response);
    if (response.status === 401 && options.token) options.onUnauthorized?.();
    throw error;
  }

  return (await response.json()) as T;
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  options: ApiRequestOptions = {},
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: requestHeaders(options.token, true),
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      `Cannot reach the DeviceOps API at ${API_BASE_URL}.`,
      null,
    );
  }

  if (!response.ok) {
    const error = await responseError(response);
    if (response.status === 401 && options.token) options.onUnauthorized?.();
    throw error;
  }

  return (await response.json()) as T;
}

export async function apiPatch<T>(
  path: string,
  body: unknown,
  options: ApiRequestOptions = {},
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "PATCH",
      headers: requestHeaders(options.token, true),
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      `Cannot reach the DeviceOps API at ${API_BASE_URL}.`,
      null,
    );
  }

  if (!response.ok) {
    const error = await responseError(response);
    if (response.status === 401 && options.token) options.onUnauthorized?.();
    throw error;
  }

  return (await response.json()) as T;
}

export async function apiDelete(
  path: string,
  options: ApiRequestOptions = {},
): Promise<void> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "DELETE",
      headers: requestHeaders(options.token),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      `Cannot reach the DeviceOps API at ${API_BASE_URL}.`,
      null,
    );
  }

  if (!response.ok) {
    const error = await responseError(response);
    if (response.status === 401 && options.token) options.onUnauthorized?.();
    throw error;
  }
}
