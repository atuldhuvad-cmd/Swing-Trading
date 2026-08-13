import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MasterData from './MasterData';
import RecommendationEntry from './RecommendationEntry';

afterEach(cleanup);

describe('Frontend Pages', () => {
  it('Master Data renders brokers and stocks', () => {
    render(<MemoryRouter><MasterData /></MemoryRouter>);
    expect(screen.getByText('Master Data')).toBeDefined();
    expect(screen.getByText(/Brokers/)).toBeDefined();
    expect(screen.getByText(/Stocks/)).toBeDefined();
  });

  it('Recommendation Entry renders fields', () => {
    render(<MemoryRouter><RecommendationEntry /></MemoryRouter>);
    expect(screen.getByText('New Recommendation')).toBeDefined();
    expect(screen.getByText('Stock')).toBeDefined();
    expect(screen.getByText('Broker')).toBeDefined();
    expect(screen.getByText('Rating')).toBeDefined();
  });

  it('Required field validation for recommendation entry', async () => {
    render(<MemoryRouter><RecommendationEntry /></MemoryRouter>);
    
    const saveButton = screen.getByRole('button', { name: /Save Recommendation/i });
    fireEvent.click(saveButton);
    
    // Should show error for required fields
    const error = await screen.findByText('Please fill all required fields');
    expect(error).toBeDefined();
  });
});
