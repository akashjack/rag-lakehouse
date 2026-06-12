import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, ChunkResult } from '../../services/api.service';

@Component({
  selector: 'app-query',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './query.component.html',
  styleUrl: './query.component.scss'
})
export class QueryComponent {
  question = '';
  mode = 'hybrid';
  k = 5;

  loading = signal(false);
  answer = signal('');
  sources = signal<ChunkResult[]>([]);
  searchResults = signal<ChunkResult[]>([]);
  error = signal('');

  constructor(private api: ApiService) {}

  async ask() {
    if (!this.question.trim()) return;
    this.loading.set(true);
    this.answer.set('');
    this.sources.set([]);
    this.error.set('');

    try {
      const reader = await this.api.fetchAsk(this.question, this.k, this.mode);
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            const data = line.slice(5).trim();
            try {
              const parsed = JSON.parse(data);
              if (currentEvent === 'token' && typeof parsed === 'string') {
                this.answer.update(a => a + parsed);
              } else if (currentEvent === 'citations' && Array.isArray(parsed)) {
                this.sources.set(parsed);
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      this.error.set(e?.message ?? 'Request failed');
    } finally {
      this.loading.set(false);
    }
  }

  search() {
    if (!this.question.trim()) return;
    this.loading.set(true);
    this.searchResults.set([]);
    this.error.set('');

    this.api.search(this.question, this.k, this.mode).subscribe({
      next: res => {
        this.searchResults.set(res.results);
        this.loading.set(false);
      },
      error: e => {
        this.error.set(e?.message ?? 'Search failed');
        this.loading.set(false);
      }
    });
  }
}
