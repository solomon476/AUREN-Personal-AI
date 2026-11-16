import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession } from './helpers';

test.describe('Long-term Memory Explorer & Epistemic Verification E2E', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuthenticatedSession(page);
  });

  test('navigates to /memories via sidebar and renders explorer view', async ({ page }) => {
    // Intercept memory listing
    await page.route('**/api/v1/memories*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'mem-101',
              content: 'User prefers functional TypeScript programming patterns.',
              memory_type: 'preference',
              category: 'technical',
              importance: 4,
              confidence: 0.92,
              confirmation_status: 'confirmed',
              lifecycle_status: 'active',
              origin: 'user_direct_input',
              access_count: 3,
              created_at: '2026-11-16T12:00:00Z',
              updated_at: '2026-11-16T12:00:00Z',
            },
            {
              id: 'mem-102',
              content: 'User is leading development of the AUREN AI assistant.',
              memory_type: 'project',
              category: 'work',
              importance: 5,
              confidence: 0.85,
              confirmation_status: 'unconfirmed',
              lifecycle_status: 'active',
              origin: 'chat_inferred',
              access_count: 1,
              created_at: '2026-11-16T13:00:00Z',
              updated_at: '2026-11-16T13:00:00Z',
            },
          ],
          total: 2,
          page: 1,
          page_size: 12,
          has_more: false,
        }),
      });
    });

    await page.goto('/chat');
    // Click on Long-term Memory link in navigation sidebar
    const memoryLink = page.getByRole('link', { name: /long-term memory/i });
    await expect(memoryLink).toBeVisible();
    await memoryLink.click();

    await expect(page).toHaveURL(/\/memories/);
    await expect(page.getByRole('heading', { name: /long-term memory explorer/i })).toBeVisible();

    // Verify memories appear on page
    await expect(page.getByText('User prefers functional TypeScript programming patterns.')).toBeVisible();
    await expect(page.getByText('User is leading development of the AUREN AI assistant.')).toBeVisible();

    // Verify status badges
    await expect(page.locator('span', { hasText: 'Confirmed' }).first()).toBeVisible();
    await expect(page.locator('span', { hasText: 'Inference' }).first()).toBeVisible();
  });

  test('searches and filters memories', async ({ page }) => {
    let capturedUrl = '';
    await page.route('**/api/v1/memories*', async (route) => {
      capturedUrl = route.request().url();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'mem-101',
              content: 'User prefers functional TypeScript programming patterns.',
              memory_type: 'preference',
              category: 'technical',
              importance: 4,
              confirmation_status: 'confirmed',
              lifecycle_status: 'active',
              origin: 'user_direct_input',
              access_count: 1,
              created_at: '2026-11-16T12:00:00Z',
              updated_at: '2026-11-16T12:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 12,
          has_more: false,
        }),
      });
    });

    await page.goto('/memories');
    await expect(page.getByRole('heading', { name: /long-term memory explorer/i })).toBeVisible();

    // Type in search box
    const searchInput = page.getByPlaceholder(/search memory content/i);
    await searchInput.fill('TypeScript');

    await expect.poll(() => capturedUrl).toContain('query=TypeScript');

    // Filter by type
    const typeSelect = page.getByLabel('Filter by memory type');
    await typeSelect.selectOption('preference');

    await expect.poll(() => capturedUrl).toContain('memory_type=preference');
  });

  test('opens memory detail modal and confirms an unconfirmed inference', async ({ page }) => {
    let confirmedCalled = false;

    await page.route('**/api/v1/memories*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'mem-201',
              content: 'Tentative inference: User prefers automated testing over manual QA.',
              memory_type: 'preference',
              category: 'technical',
              importance: 4,
              confidence: 0.78,
              confirmation_status: 'unconfirmed',
              lifecycle_status: 'active',
              origin: 'chat_inferred',
              access_count: 1,
              created_at: '2026-11-16T14:00:00Z',
              updated_at: '2026-11-16T14:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 12,
          has_more: false,
        }),
      });
    });

    await page.route('**/api/v1/memories/mem-201/confirm', async (route) => {
      confirmedCalled = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'mem-201',
          content: 'Tentative inference: User prefers automated testing over manual QA.',
          memory_type: 'preference',
          category: 'technical',
          importance: 4,
          confidence: 1.0,
          confirmation_status: 'confirmed',
          lifecycle_status: 'active',
          origin: 'chat_inferred',
          access_count: 1,
          last_confirmed_at: new Date().toISOString(),
          created_at: '2026-11-16T14:00:00Z',
          updated_at: new Date().toISOString(),
        }),
      });
    });

    await page.goto('/memories');
    await expect(page.getByText('Tentative inference: User prefers automated testing over manual QA.')).toBeVisible();

    // Click card to open detail modal
    await page.getByText('Tentative inference: User prefers automated testing over manual QA.').click();

    // Modal dialog is visible
    const dialog = page.getByRole('dialog', { name: /memory details/i });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/Unconfirmed Inference/i)).toBeVisible();
    await expect(dialog.getByText(/Not yet confirmed by you/i)).toBeVisible();

    // Click Confirm Inference
    const confirmButton = dialog.getByRole('button', { name: /confirm inference/i });
    await confirmButton.click();

    await expect.poll(() => confirmedCalled).toBe(true);
    await expect(dialog.getByText(/Confirmed Fact/i)).toBeVisible();
  });

  test('corrects inaccurate memory preserving historical lineage', async ({ page }) => {
    let correctPayload: any = null;

    await page.route('**/api/v1/memories*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'mem-301',
              content: 'User relocated to Seattle.',
              memory_type: 'fact',
              category: 'personal',
              importance: 3,
              confirmation_status: 'confirmed',
              lifecycle_status: 'active',
              origin: 'user_direct_input',
              access_count: 2,
              created_at: '2026-11-16T10:00:00Z',
              updated_at: '2026-11-16T10:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 12,
          has_more: false,
        }),
      });
    });

    await page.route('**/api/v1/memories/mem-301/correct', async (route) => {
      correctPayload = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'mem-302',
          content: correctPayload.content,
          memory_type: correctPayload.memory_type || 'fact',
          category: correctPayload.category || 'personal',
          importance: correctPayload.importance || 3,
          confirmation_status: 'confirmed',
          lifecycle_status: 'active',
          origin: 'user_direct_edit',
          previous_version_id: 'mem-301',
          root_memory_id: 'mem-301',
          access_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });

    await page.goto('/memories');
    await page.getByText('User relocated to Seattle.').click();

    const dialog = page.getByRole('dialog', { name: /memory details/i });
    await expect(dialog).toBeVisible();

    // Click Correct Memory button
    await dialog.getByRole('button', { name: /correct memory/i }).click();

    await expect(dialog.getByText(/Preserves Historical Lineage/i)).toBeVisible();
    const textarea = dialog.getByPlaceholder(/corrected memory content/i);
    await textarea.fill('User relocated to San Francisco.');

    await dialog.getByRole('button', { name: /save lineage-preserving correction/i }).click();

    await expect.poll(() => correctPayload).not.toBeNull();
    expect(correctPayload.content).toBe('User relocated to San Francisco.');

    // Verifies new memory displays lineage
    await expect(dialog.getByText('User relocated to San Francisco.')).toBeVisible();
    await expect(dialog.getByText('mem-301')).toBeVisible();
  });

  test('inspects conversation context provenance in chat interface', async ({ page }) => {
    // Intercept conversations
    await page.route('**/api/v1/chat/conversations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'conv-context-e2e',
            title: 'Technical Discussion',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 2,
          },
        ]),
      });
    });

    // Intercept messages
    await page.route('**/api/v1/chat/conversations/conv-context-e2e/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'msg-u1',
            conversation_id: 'conv-context-e2e',
            role: 'user',
            content: 'How should we architect the state machine?',
            created_at: new Date().toISOString(),
          },
          {
            id: 'msg-a1',
            conversation_id: 'conv-context-e2e',
            role: 'assistant',
            content: 'Use an explicit state transition matrix with immutable terminal states.',
            created_at: new Date().toISOString(),
            metadata: {
              model: 'gemini-1.5-pro-preview',
            },
          },
        ]),
      });
    });

    // Intercept message context
    await page.route('**/api/v1/chat/conversations/conv-context-e2e/messages/msg-a1/context', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          message_id: 'msg-a1',
          conversation_id: 'conv-context-e2e',
          model: 'gemini-1.5-pro-preview',
          memory_count: 1,
          retrieved_memories: [
            {
              id: 'mem-context-ref-1',
              content: 'User designs systems with strict mathematical invariants.',
              memory_type: 'preference',
              category: 'technical',
              confirmation_status: 'confirmed',
              importance: 5,
              score: 0.94,
            },
          ],
        }),
      });
    });

    await page.goto('/chat/conv-context-e2e');
    await expect(page.getByText('Use an explicit state transition matrix with immutable terminal states.')).toBeVisible();

    // Click "Context Inspector" button on the assistant bubble
    const inspectButton = page.getByRole('button', { name: /inspect context provenance/i });
    await expect(inspectButton).toBeVisible();
    await inspectButton.click();

    // Verify Context Inspector modal opens
    const inspectorDialog = page.getByRole('dialog', { name: /context inspector & memory provenance/i });
    await expect(inspectorDialog).toBeVisible();

    // Verify model, memory content, similarity score, and journal isolation notice
    await expect(inspectorDialog.getByText('gemini-1.5-pro-preview')).toBeVisible();
    await expect(inspectorDialog.getByText('User designs systems with strict mathematical invariants.')).toBeVisible();
    await expect(inspectorDialog.getByText('94%')).toBeVisible();
    await expect(inspectorDialog.getByText(/strict journal isolation/i)).toBeVisible();
  });
});
