import { Component } from '@angular/core';
import { QueryComponent } from './components/query/query.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [QueryComponent],
  template: '<app-query />',
})
export class App {}
