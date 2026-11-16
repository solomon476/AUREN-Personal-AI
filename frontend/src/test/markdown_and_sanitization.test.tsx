/**
 * Test Suite: Rich Markdown Rendering, KaTeX Math, Code Highlighting,
 * and Adversarial Security Sanitization.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageContent } from '../components/chat/MessageContent';

describe('Rich Markdown and Code Rendering', () => {
  it('renders structured markdown headings, lists, tables, and blockquotes', () => {
    const markdownContent = `
# Main Header
## Sub Header
### Section Header

Here is a paragraph with **bold text**, *italic text*, and ~~strikethrough~~.

- Unordered item 1
- Unordered item 2

1. Ordered step 1
2. Ordered step 2

> This is an important blockquote reflection.

| Feature | Status | Tier |
| :--- | :---: | ---: |
| Memory | Active | Primary |
| Chat | Streaming | Core |
`;

    const { container } = render(<MessageContent content={markdownContent} role="assistant" />);

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Main Header');
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Sub Header');
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Section Header');

    expect(screen.getByText('Unordered item 1')).toBeInTheDocument();
    expect(screen.getByText('Ordered step 1')).toBeInTheDocument();

    const blockquote = container.querySelector('blockquote');
    expect(blockquote).toBeInTheDocument();
    expect(blockquote).toHaveTextContent('This is an important blockquote reflection.');

    const table = container.querySelector('table');
    expect(table).toBeInTheDocument();
    expect(screen.getByText('Feature')).toBeInTheDocument();
    expect(screen.getByText('Memory')).toBeInTheDocument();
  });

  it('renders fenced code blocks with language badge and copy action', () => {
    const codeSnippet = `
\`\`\`typescript
interface UserProfile {
  id: string;
  email: string;
}
\`\`\`
`;
    const { container } = render(<MessageContent content={codeSnippet} role="assistant" />);

    expect(screen.getByText('typescript')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy code to clipboard/i })).toBeInTheDocument();
    expect(container.textContent).toContain('interface UserProfile');
  });

  it('renders inline code with distinct monospace styling', () => {
    const inlineSnippet = 'Please inspect the `vector(768)` PostgreSQL column.';
    const { container } = render(<MessageContent content={inlineSnippet} role="assistant" />);

    const inlineCode = container.querySelector('code');
    expect(inlineCode).toBeInTheDocument();
    expect(inlineCode).toHaveTextContent('vector(768)');
    expect(inlineCode?.className).toContain('font-mono');
  });

  it('renders mathematical notation through KaTeX', () => {
    const mathContent = 'Inline math: $E = mc^2$\n\nBlock formula:\n\n$$\\frac{a}{b} = c$$';
    const { container } = render(<MessageContent content={mathContent} role="assistant" />);

    // Verify KaTeX container classes are rendered
    const katexElements = container.querySelectorAll('.katex');
    expect(katexElements.length).toBeGreaterThan(0);
    expect(container.querySelector('math')).not.toBeNull();
  });

  it('renders safe links with target=_blank and rel=noopener', () => {
    const linkContent = 'Visit [AUREN Docs](https://auren.ai/docs) for details.';
    render(<MessageContent content={linkContent} role="assistant" />);

    const link = screen.getByRole('link', { name: /auren docs/i });
    expect(link).toHaveAttribute('href', 'https://auren.ai/docs');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('preserves plain whitespace formatting for user messages without markdown parsing', () => {
    const rawUserMessage = '# Not a real heading\n  Two spaces indent\n<script>console.log("hello")</script>';
    const { container } = render(<MessageContent content={rawUserMessage} role="user" />);

    // In user mode, it should NOT render an <h1> element
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    expect(container.textContent).toContain('# Not a real heading');
    expect(container.textContent).toContain('<script>console.log("hello")</script>');
  });
});

describe('Adversarial Security Sanitization', () => {
  it('neutralizes executable <script> tags from assistant content', () => {
    const maliciousPayload = 'Assistant reply\n\n<script>window.__pwned__ = true;</script>\n\nSafe text continuation.';
    const { container } = render(<MessageContent content={maliciousPayload} role="assistant" />);

    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText(/Assistant reply/)).toBeInTheDocument();
    expect(screen.getByText(/Safe text continuation/)).toBeInTheDocument();
    expect((window as any).__pwned__).toBeUndefined();
  });

  it('neutralizes inline event handler injection (onload, onerror, onclick)', () => {
    const eventHandlerPayload = `
<img src="x" onerror="window.__xss_event__ = 1" />
<button onclick="window.__click_xss__ = 1">Click Me</button>
<div onmouseover="window.__hover_xss__ = 1">Hover</div>
`;
    const { container } = render(<MessageContent content={eventHandlerPayload} role="assistant" />);

    // Event handlers must be completely stripped
    const allElements = container.querySelectorAll('*');
    allElements.forEach((el) => {
      expect(el.getAttribute('onerror')).toBeNull();
      expect(el.getAttribute('onclick')).toBeNull();
      expect(el.getAttribute('onmouseover')).toBeNull();
    });
    expect((window as any).__xss_event__).toBeUndefined();
  });

  it('neutralizes dangerous URL schemes (javascript:, data:, vbscript:)', () => {
    const dangerousLinks = `
[Dangerous JS](javascript:alert("xss"))
[Dangerous Data](data:text/html,<script>alert(1)</script>)
[Dangerous VBScript](vbscript:msgbox("hi"))
[Legitimate Link](https://safe.example.com)
`;
    const { container } = render(<MessageContent content={dangerousLinks} role="assistant" />);

    const links = container.querySelectorAll('a');
    links.forEach((a) => {
      const href = a.getAttribute('href');
      if (href) {
        expect(href).not.toMatch(/^javascript:/i);
        expect(href).not.toMatch(/^data:/i);
        expect(href).not.toMatch(/^vbscript:/i);
      }
    });

    const safeLink = screen.getByRole('link', { name: /legitimate link/i });
    expect(safeLink).toHaveAttribute('href', 'https://safe.example.com');
  });

  it('neutralizes dangerous iframe, object, and embed inclusions', () => {
    const embedPayload = `
<iframe src="https://attacker.com/cookie-stealer"></iframe>
<object data="malicious.swf"></object>
<embed src="malicious.pdf" />
`;
    const { container } = render(<MessageContent content={embedPayload} role="assistant" />);

    expect(container.querySelector('iframe')).toBeNull();
    expect(container.querySelector('object')).toBeNull();
    expect(container.querySelector('embed')).toBeNull();
  });
});
