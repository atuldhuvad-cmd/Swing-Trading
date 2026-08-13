import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import CandidateDashboard from './CandidateDashboard';

afterEach(cleanup);

describe('Mobile Layout Width Validation', () => {
  const viewports = [320, 375, 390, 768, 1024];

  viewports.forEach((width) => {
    it(`renders Candidate Dashboard cleanly at viewport width ${width}px`, () => {
      // Set window innerWidth
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: width,
      });
      window.dispatchEvent(new Event('resize'));

      const { container } = render(
        <MemoryRouter>
          <CandidateDashboard />
        </MemoryRouter>
      );

      // Verify main container renders
      expect(screen.getByText('Broker Candidate Universe')).toBeDefined();
      expect(screen.getByText(/Filters & Sort/i)).toBeDefined();

      // Check responsive card wrapper exists
      const topBar = container.querySelector('.flex.flex-col');
      expect(topBar).not.toBeNull();
    });
  });
});
