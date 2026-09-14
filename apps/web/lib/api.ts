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

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal,
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
    let detail = `The API returned HTTP ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // The status code is sufficient when the response is not JSON.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}
