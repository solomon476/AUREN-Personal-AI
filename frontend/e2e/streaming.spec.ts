import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession } from './helpers';

test.describe('Conversation Streaming & Controls', () => {
  test('sending a prompt streams assistant tokens into the chat workspace', async ({ page }) => {
    await setupAuthenticatedSession(page);

    await page.route('**/api/v1/chat/conversations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/chat/conversations/conv-stream-1/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'u1',
            conversation_id: 'conv-stream-1',
            role: 'user',
            content: 'Explain quantum mechanics',
            created_at: new Date().toISOString(),
          },
          {
            id: 'a1',
            conversation_id: 'conv-stream-1',
            role: 'assistant',
            content: 'Quantum entanglement is a physical phenomenon.',
            created_at: new Date().toISOString(),
          },
        ]),
      });
    });

    await page.route('**/api/v1/chat/completions', async (route) => {
      // Stream mock SSE response
      const sseBody = [
        'event: metadata\ndata: {"conversation_id": "conv-stream-1", "user_message_id": "u1", "title": "Quantum Stream"}\n\n',
        'event: token\ndata: {"text": "Quantum "}\n\n',
        'event: token\ndata: {"text": "entanglement is a "}\n\n',
        'event: token\ndata: {"text": "physical phenomenon."}\n\n',
        'event: done\ndata: {"message_id": "a1", "finish_reason": "stop"}\n\n',
      ].join('');

      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: sseBody,
      });
    });

    await page.goto('/chat');

    const input = page.getByPlaceholder(/ask auren anything/i);
    await input.fill('Explain quantum mechanics');
    await page.getByRole('button', { name: /send message/i }).click();

    // Verify user bubble appears
    await expect(page.getByText('Explain quantum mechanics')).toBeVisible();

    // Verify streamed tokens assemble into assistant bubble
    await expect(page.getByText(/Quantum entanglement is a physical phenomenon/).first()).toBeVisible();
  });
});
