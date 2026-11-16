import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession } from './helpers';

test.describe('Conversation Rendering: Markdown, KaTeX & Sanitization', () => {
  test('renders markdown, syntax-highlighted code, KaTeX math, and neutralizes XSS', async ({ page }) => {
    await setupAuthenticatedSession(page);

    const complexAssistantMessage = `
# Executive Overview

This is **bold** text and *italic* text.

### Architecture Table

| Module | Status | Dimension |
| :--- | :--- | :--- |
| Memory | Operational | 768 |
| Hybrid | Active | Vector+BM25 |

### Mathematical Formulation

Inline math: $E = mc^2$

### Implementation

\`\`\`typescript
export interface EmbeddingModel {
  name: string;
  dimension: number;
}
\`\`\`

### Adversarial Payloads

<script>window.__e2e_xss__ = true;</script>

<img src="x" onerror="window.__img_xss__ = true;" />

[Unsafe Link](javascript:alert(1))

[Safe Link](https://auren.ai)
`;

    await page.route('**/api/v1/chat/conversations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'conv-render-1',
            title: 'Rendering Verification',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 1,
          },
        ]),
      });
    });

    await page.route('**/api/v1/chat/conversations/conv-render-1/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'msg-render-1',
            conversation_id: 'conv-render-1',
            role: 'assistant',
            content: complexAssistantMessage,
            created_at: new Date().toISOString(),
          },
        ]),
      });
    });

    await page.goto('/chat/conv-render-1');

    // 1. Verify Headings
    await expect(page.getByRole('heading', { level: 1, name: /executive overview/i })).toBeVisible();
    await expect(page.getByRole('heading', { level: 3, name: /architecture table/i })).toBeVisible();

    // 2. Verify Table
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByText('Vector+BM25')).toBeVisible();

    // 3. Verify KaTeX Math
    await expect(page.locator('.katex').first()).toBeVisible();

    // 4. Verify Code Block
    await expect(page.getByText('typescript')).toBeVisible();
    await expect(page.getByRole('button', { name: /copy code to clipboard/i })).toBeVisible();

    // 5. Verify Safe Link
    const safeLink = page.getByRole('link', { name: /safe link/i });
    await expect(safeLink).toBeVisible();
    await expect(safeLink).toHaveAttribute('href', 'https://auren.ai');

    // 6. Verify XSS Neutralization
    const pwned = await page.evaluate(() => (window as any).__e2e_xss__);
    const imgPwned = await page.evaluate(() => (window as any).__img_xss__);
    expect(pwned).toBeUndefined();
    expect(imgPwned).toBeUndefined();

    // Verify javascript: link was neutralized
    const unsafeLink = page.locator('a[href^="javascript:"]');
    await expect(unsafeLink).toHaveCount(0);
  });
});
