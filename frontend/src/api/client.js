async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json", ...options.headers },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

export function getAlerts(limit = 50) {
  return request(`/api/alerts?limit=${encodeURIComponent(limit)}`);
}

export function searchLocations(query) {
  return request(`/api/search?q=${encodeURIComponent(query)}`);
}

export function getReadiness() {
  return request("/api/meta");
}
