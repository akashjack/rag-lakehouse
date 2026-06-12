import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ChunkResult {
  chunk_id: string;
  doc_id: string;
  source: string;
  chunk_index: number;
  title: string | null;
  source_url: string | null;
  score: number;
  text_head: string | null;
}

export interface SearchResponse {
  query: string;
  mode: string;
  results: ChunkResult[];
}

export interface HealthResponse {
  status: string;
  oracle: string;
  ollama: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.base}/health`);
  }

  search(query: string, k = 5, mode = 'hybrid'): Observable<SearchResponse> {
    return this.http.get<SearchResponse>(
      `${this.base}/search?q=${encodeURIComponent(query)}&k=${k}&mode=${mode}`
    );
  }

  askStream(question: string, k = 5, mode = 'hybrid'): EventSource {
    // SSE via EventSource is GET-only; we use a workaround:
    // POST to /ask and read the stream via fetch in the component.
    // This method is a placeholder — actual streaming is done via fetchAsk().
    throw new Error('Use fetchAsk() for SSE streaming');
  }

  fetchAsk(question: string, k = 5, mode = 'hybrid'): Promise<ReadableStreamDefaultReader<Uint8Array>> {
    return fetch(`${this.base}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, k, mode }),
    }).then(r => r.body!.getReader());
  }
}
