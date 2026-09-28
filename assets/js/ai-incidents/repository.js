export class IncidentRepository {
  constructor(baseUrl = "/data/ai-incidents/public") {
    this.baseUrl = baseUrl;
  }

  async request(path) {
    const response = await fetch(`${this.baseUrl}/${path}`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Incident data request failed (${response.status})`);
    return response.json();
  }

  summary() {
    return this.request("summary.json");
  }

  map() {
    return this.request("map.json");
  }

  page(page = 1) {
    return this.request(`incidents-page-${Math.max(1, Number(page) || 1)}.json`);
  }

  async all() {
    const first = await this.page(1);
    const pageCount = Math.max(1, Math.ceil(first.total / first.pageSize));
    const remaining = await Promise.all(Array.from({ length: pageCount - 1 }, (_, index) => this.page(index + 2)));
    return { ...first, items: [first, ...remaining].flatMap((page) => page.items) };
  }
}
