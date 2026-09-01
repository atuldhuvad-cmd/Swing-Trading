import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import BackLink from './BackLink';

describe('BackLink', () => {
  it('uses in-app history when a previous page exists', () => {
    render(
      <MemoryRouter initialEntries={['/final-candidates', '/evidence/1']} initialIndex={1}>
        <Routes>
          <Route path="/final-candidates" element={<div>Eval page</div>} />
          <Route path="/evidence/1" element={<BackLink fallback="/final-candidates" />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Back/ }));
    expect(screen.getByText('Eval page')).toBeDefined();
  });

  it('uses fallback on deep-link with no previous app page', () => {
    render(
      <MemoryRouter initialEntries={['/evidence/1']}>
        <Routes>
          <Route path="/final-candidates" element={<div>Eval fallback</div>} />
          <Route path="/evidence/1" element={<BackLink fallback="/final-candidates" />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Back/ }));
    expect(screen.getByText('Eval fallback')).toBeDefined();
  });

  it('consensus fallback is home', () => {
    render(
      <MemoryRouter initialEntries={['/consensus/4']}>
        <Routes>
          <Route path="/" element={<div>Broker Opinion Universe</div>} />
          <Route path="/consensus/4" element={<BackLink fallback="/" />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Back/ }));
    expect(screen.getByText('Broker Opinion Universe')).toBeDefined();
  });
});
