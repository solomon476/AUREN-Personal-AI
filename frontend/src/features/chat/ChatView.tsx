/**
 * Persistent Chat & Streaming Conversational View.
 * Enhanced with Rich Markdown & Code Rendering, Conversation Rename/Delete Lifecycle,
 * Resilient SSE Reconnection with Exponential Backoff, and Mobile-First Responsive Architecture.
 * Elevated with High-Contrast White, Obsidian, Emerald, and Gold Design System.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  Send,
  Square,
  Plus,
  MessageSquare,
  Bot,
  User,
  Sparkles,
  AlertCircle,
  Loader2,
  RotateCcw,
  Edit2,
  Trash2,
  Brain,
  X,
} from 'lucide-react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { useSafeSearch } from '../../hooks/useSafeSearch';
import {
  ChatMessage,
  streamChat
} from '../../api/chat';
import { useAuth } from '../../context/AuthContext';
import {
  useConversations,
  useCreateConversation,
  useRenameConversation,
  useDeleteConversation
} from '../../hooks/useConversations';
import { useConversationMessages, useInvalidateMessages } from '../../hooks/useConversationMessages';
import { MessageContent } from '../../components/chat/MessageContent';
import { RenameConversationModal } from '../../components/chat/RenameConversationModal';
import { DeleteConversationModal } from '../../components/chat/DeleteConversationModal';
import { ContextInspectorModal } from '../../components/chat/ContextInspectorModal';
import { AuthModal } from '../../components/auth/AuthModal';

interface ChatViewProps {
  conversationId?: string;
}

export const ChatView: React.FC<ChatViewProps> = ({ conversationId: propConversationId }) => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const routeParams = useParams({ strict: false }) as { conversationId?: string };

  const activeConversationId = propConversationId || routeParams?.conversationId || null;

  // TanStack Query Hooks for Server State Caching & Mutations
  const { data: conversations = [], isLoading: isLoadingConversations } = useConversations(user?.id);
  const createConversationMutation = useCreateConversation(user?.id);
  const renameConversationMutation = useRenameConversation(user?.id);
  const deleteConversationMutation = useDeleteConversation(user?.id);

  const {
    data: fetchedMessages,
    isLoading: isLoadingMessages,
    error: messagesError
  } = useConversationMessages(user?.id, activeConversationId || undefined);
  const invalidateMessages = useInvalidateMessages();

  const searchParams = useSafeSearch<{ q?: string; prompt?: string }>();
  const initialPrompt = searchParams?.q || searchParams?.prompt || '';

  // Local State for interactive stream accumulation, modals, and input
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState(initialPrompt);

  useEffect(() => {
    if (initialPrompt && !inputValue) {
      setInputValue(initialPrompt);
    }
  }, [initialPrompt]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [reconnectStatus, setReconnectStatus] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pendingRetry, setPendingRetry] = useState<{
    message: string;
    conversationId?: string;
    idempotencyKey: string;
  } | null>(null);

  // Modals and Drawers
  const [isMobileThreadDrawerOpen, setIsMobileThreadDrawerOpen] = useState(false);
  const [isRenameModalOpen, setIsRenameModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [contextInspectorMessageId, setContextInspectorMessageId] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messageContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  const handleScroll = () => {
    if (!messageContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = messageContainerRef.current;
    isAtBottomRef.current = scrollHeight - scrollTop - clientHeight < 100;
  };

  const scrollToBottom = (instant = false) => {
    messagesEndRef.current?.scrollIntoView({ behavior: instant ? 'auto' : 'smooth' });
  };

  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollToBottom(isStreaming);
    }
  }, [messages, streamingContent, reconnectStatus, isStreaming]);

  // Sync server-cached messages into local state when conversation loads
  useEffect(() => {
    if (fetchedMessages) {
      setMessages(fetchedMessages);
    } else if (!activeConversationId) {
      setMessages([]);
    }
  }, [fetchedMessages, activeConversationId]);

  // Clear transient error message when switching conversations
  useEffect(() => {
    setErrorMessage(null);
  }, [activeConversationId]);

  // Handle invalid conversation ID or fetch failure safely
  useEffect(() => {
    if (messagesError) {
      setErrorMessage(
        messagesError instanceof Error ? messagesError.message : 'Could not load conversation messages'
      );
    }
  }, [messagesError]);

  const handleNewConversation = async () => {
    if (isStreaming) return;
    if (!user) {
      setIsAuthModalOpen(true);
      return;
    }
    try {
      const newConv = await createConversationMutation.mutateAsync('New Conversation');
      setMessages([]);
      setErrorMessage(null);
      setIsMobileThreadDrawerOpen(false);
      navigate({ to: '/chat/$conversationId', params: { conversationId: newConv.id } });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to create conversation');
    }
  };

  const handleSelectConversation = (id: string) => {
    if (isStreaming) return;
    setErrorMessage(null);
    setIsMobileThreadDrawerOpen(false);
    navigate({ to: '/chat/$conversationId', params: { conversationId: id } });
  };

  const handleRenameConfirm = async (newTitle: string) => {
    if (!activeConversationId) return;
    await renameConversationMutation.mutateAsync({
      conversationId: activeConversationId,
      title: newTitle,
    });
  };

  const handleDeleteConfirm = async () => {
    if (!activeConversationId) return;
    const targetId = activeConversationId;
    await deleteConversationMutation.mutateAsync(targetId);
    setMessages([]);
    setStreamingContent('');
    navigate({ to: '/chat' });
  };

  /**
   * Resilient SSE streaming with bounded exponential backoff reconnection.
   */
  const MAX_RETRIES = 3;
  const executeChatStream = async (
    messageText: string,
    targetConversationId: string | undefined,
    idempotencyKey: string,
    attempt = 0,
  ) => {
    setIsStreaming(true);
    setErrorMessage(null);
    let accumulatedContent = '';
    if (attempt === 0) {
      setStreamingContent('');
    }
    abortControllerRef.current = new AbortController();

    try {
      await streamChat(
        messageText,
        targetConversationId,
        {
          onMetadata: (meta) => {
            setReconnectStatus(null);
            if (!activeConversationId || activeConversationId !== meta.conversation_id) {
              navigate({ to: '/chat/$conversationId', params: { conversationId: meta.conversation_id } });
            }
          },
          onToken: (token) => {
            setReconnectStatus(null);
            accumulatedContent += token;
            setStreamingContent(accumulatedContent);
          },
          onDone: (done) => {
            const assistantMessage: ChatMessage = {
              id: done?.message_id || `assistant-${Date.now()}`,
              conversation_id: activeConversationId || '',
              role: 'assistant',
              content: accumulatedContent,
              created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, assistantMessage]);
            setStreamingContent('');
            setPendingRetry(null);
            setIsStreaming(false);
            setReconnectStatus(null);

            if (activeConversationId) {
              invalidateMessages(user?.id, activeConversationId);
            }
          },
          onError: (err) => {
            throw new Error(err);
          },
        },
        abortControllerRef.current.signal,
        idempotencyKey,
      );
    } catch (err: any) {
      if (abortControllerRef.current?.signal.aborted) {
        setIsStreaming(false);
        setReconnectStatus(null);
        return;
      }

      const errMsg = err instanceof Error ? err.message : String(err);
      const isNonRetryable =
        errMsg.includes('404') ||
        errMsg.includes('409') ||
        errMsg.includes('413') ||
        errMsg.includes('401') ||
        errMsg.includes('access denied') ||
        errMsg.includes('conflicting request parameters') ||
        errMsg.includes('Failed to reach backend API') ||
        errMsg.includes('Unable to connect') ||
        errMsg.includes('AI service is unavailable') ||
        errMsg.includes('unsupported_model_configuration');

      if (!isNonRetryable && attempt < MAX_RETRIES) {
        const nextAttempt = attempt + 1;
        const backoffDelay = Math.min(1000 * Math.pow(2, attempt), 5000);
        setReconnectStatus(`Connection interrupted. Reconnecting (attempt ${nextAttempt} of ${MAX_RETRIES})...`);

        await new Promise((resolve) => setTimeout(resolve, backoffDelay));
        if (!abortControllerRef.current?.signal.aborted) {
          return executeChatStream(messageText, targetConversationId, idempotencyKey, nextAttempt);
        }
      }

      setErrorMessage(errMsg || 'Streaming failed');
      setReconnectStatus(null);
      setPendingRetry({ message: messageText, conversationId: targetConversationId, idempotencyKey });
      setIsStreaming(false);
    }
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed || isStreaming) return;

    if (!user) {
      setIsAuthModalOpen(true);
      return;
    }

    const idempotencyKey = `req-${crypto.randomUUID()}`;
    setInputValue('');

    const tempUserMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: activeConversationId || '',
      role: 'user',
      content: trimmed,
      idempotency_key: idempotencyKey,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    await executeChatStream(trimmed, activeConversationId || undefined, idempotencyKey);
  };

  const handleRetry = async () => {
    if (!pendingRetry || isStreaming) return;
    await executeChatStream(pendingRetry.message, pendingRetry.conversationId, pendingRetry.idempotencyKey);
  };

  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
      setReconnectStatus(null);
    }
  };

  const activeConv = conversations.find((c) => c.id === activeConversationId);

  // Common Thread List Renderer (shared between Desktop Sidebar and Mobile Drawer)
  const renderThreadList = () => (
    <>
      <div className="p-3.5 border-b border-slate-200">
        <button
          onClick={handleNewConversation}
          disabled={isStreaming || createConversationMutation.isPending}
          className="w-full flex items-center justify-center space-x-2 py-2.5 px-3.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-sm hover:shadow-[0_0_16px_rgba(16,185,129,0.3)] transition-all duration-200 touch-target"
        >
          <Plus className="h-4 w-4" />
          <span className="tracking-wide">New Conversation</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5 scrollbar-thin">
        {isLoadingConversations ? (
          <div className="p-6 text-center text-xs text-slate-500 flex items-center justify-center space-x-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-600" />
            <span>Loading threads...</span>
          </div>
        ) : !user ? (
          <div className="p-6 text-center text-xs text-slate-500 font-normal space-y-2">
            <p>Sign in to view your conversations.</p>
            <button
              onClick={() => setIsAuthModalOpen(true)}
              className="text-xs text-emerald-600 hover:text-emerald-700 font-semibold underline"
            >
              Sign In
            </button>
          </div>
        ) : conversations.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500 font-normal">
            No conversations yet. Start one above!
          </div>
        ) : (
          conversations.map((c) => {
            const isActive = c.id === activeConversationId;
            return (
              <button
                key={c.id}
                onClick={() => handleSelectConversation(c.id)}
                className={`w-full flex items-center space-x-2.5 px-3 py-2.5 rounded-xl text-left text-xs transition-all duration-150 truncate touch-target ${
                  isActive
                    ? 'bg-emerald-50 border border-emerald-200 text-emerald-900 font-bold shadow-sm'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 border border-transparent font-medium'
                }`}
              >
                <MessageSquare className={`h-3.5 w-3.5 flex-shrink-0 ${isActive ? 'text-emerald-600' : 'text-slate-400'}`} />
                <span className="truncate flex-1">{c.title}</span>
                {typeof c.message_count === 'number' && c.message_count > 0 && (
                  <span className="text-[10px] text-slate-500 font-mono px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-semibold">
                    {c.message_count}
                  </span>
                )}
              </button>
            );
          })
        )}
      </div>
    </>
  );

  return (
    <div className="flex flex-1 h-full min-h-0 bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm transition-all duration-300">
      {/* Desktop Sidebar: Threads History */}
      <aside className="hidden md:flex flex-col w-64 sm:w-72 bg-slate-50/80 border-r border-slate-200 flex-shrink-0">
        {renderThreadList()}
      </aside>

      {/* Mobile Threads Drawer */}
      {isMobileThreadDrawerOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden animate-in fade-in duration-200">
          <div
            className="fixed inset-0 bg-slate-950/40 backdrop-blur-sm"
            onClick={() => setIsMobileThreadDrawerOpen(false)}
          />
          <div className="relative flex flex-col w-72 max-w-[85vw] bg-white shadow-2xl z-10 border-r border-slate-200">
            <div className="p-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <span className="text-xs font-bold text-slate-900">Conversation History</span>
              <button
                onClick={() => setIsMobileThreadDrawerOpen(false)}
                className="p-1.5 text-slate-500 hover:text-slate-900 rounded-lg touch-target flex items-center justify-center"
                aria-label="Close thread drawer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {renderThreadList()}
          </div>
        </div>
      )}

      {/* Main Chat Workspace */}
      <section className="flex-1 flex flex-col bg-white min-w-0">
        {/* Active Thread Header */}
        <div className="h-14 border-b border-slate-200 px-3 sm:px-5 flex items-center justify-between bg-white/95 backdrop-blur">
          <div className="flex items-center space-x-2 min-w-0">
            {/* Mobile Threads Drawer Trigger Button */}
            <button
              onClick={() => setIsMobileThreadDrawerOpen(true)}
              className="md:hidden flex items-center space-x-1 px-2.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-xs text-slate-700 hover:text-slate-900 transition touch-target flex-shrink-0 font-medium"
              aria-label="Open conversation threads"
            >
              <MessageSquare className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-[11px]">Threads</span>
            </button>

            {/* Direct New Chat Action Button (Always Accessible on Mobile & Desktop) */}
            <button
              onClick={handleNewConversation}
              disabled={isStreaming || createConversationMutation.isPending}
              className="flex items-center space-x-1 px-2.5 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 text-xs font-semibold transition touch-target flex-shrink-0 active:scale-95"
              title="Start a new dialogue"
              aria-label="Start new chat"
            >
              <Plus className="h-3.5 w-3.5 text-emerald-600" />
              <span>New Chat</span>
            </button>

            <div className="h-4 w-[1px] bg-slate-200 hidden sm:block" />

            <div className="flex items-center space-x-1.5 min-w-0">
              <h3
                onClick={!activeConv ? handleNewConversation : undefined}
                className={`text-xs sm:text-sm font-bold text-slate-900 tracking-tight truncate max-w-[110px] xs:max-w-[160px] sm:max-w-md ${
                  !activeConv ? 'cursor-pointer hover:text-emerald-600 transition' : ''
                }`}
                title={activeConv ? activeConv.title : 'Click to start new conversation'}
              >
                {activeConv ? activeConv.title : 'New Dialogue'}
              </h3>
              {activeConv && (
                <div className="flex items-center space-x-0.5 pl-0.5">
                  <button
                    onClick={() => setIsRenameModalOpen(true)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 border border-transparent hover:border-slate-200 transition touch-target flex items-center justify-center"
                    title="Rename conversation"
                    aria-label="Rename conversation"
                  >
                    <Edit2 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => setIsDeleteModalOpen(true)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 border border-transparent hover:border-rose-200 transition touch-target flex items-center justify-center"
                    title="Delete conversation"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-[10px] font-mono px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 hidden sm:inline-flex items-center space-x-1.5 font-semibold">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)] animate-pulse"></span>
              <span>Gemini Flash &bull; Sub-Second Stream</span>
            </span>
          </div>
        </div>

        {/* Message Stream Display */}
        <div
          ref={messageContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-3.5 sm:p-7 space-y-4 sm:space-y-6 scrollbar-thin bg-white"
        >
          {!user && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shadow-sm">
              <div className="flex items-center space-x-3">
                <div className="h-8 w-8 rounded-lg bg-amber-100 border border-amber-300 flex items-center justify-center text-amber-700 flex-shrink-0">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-900">Private Authenticated Assistant</h4>
                  <p className="text-slate-600 text-[11px] leading-relaxed">
                    Sign in to chat with AUREN, access persistent dialogues, and leverage memory context.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsAuthModalOpen(true)}
                className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-lg text-xs transition flex-shrink-0 touch-target self-start sm:self-center shadow-sm"
              >
                Sign In / Register
              </button>
            </div>
          )}

          {isLoadingMessages ? (
            <div className="h-full flex items-center justify-center text-slate-500 text-xs space-x-2">
              <Loader2 className="h-4 w-4 animate-spin text-emerald-600" />
              <span>Loading messages...</span>
            </div>
          ) : messages.length === 0 && !streamingContent ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-4 sm:p-6 space-y-4 sm:space-y-5">
              <div className="h-14 w-14 sm:h-16 sm:w-16 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shadow-sm">
                <Bot className="h-7 w-7 sm:h-8 sm:w-8 text-emerald-600" />
              </div>
              <div className="space-y-1.5">
                <h4 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">AUREN Personal AI Assistant</h4>
                <p className="text-xs sm:text-sm text-slate-600 max-w-sm leading-relaxed">
                  Ready to assist. Your dialogues are saved privately to your account with strict ownership enforcement.
                </p>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, index) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={msg.id || index}
                    className={`flex items-start space-x-2.5 sm:space-x-3.5 ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <div className="h-7 w-7 sm:h-8 sm:w-8 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-700 flex-shrink-0 text-xs mt-0.5 shadow-sm">
                        <Bot className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      </div>
                    )}
                    <div
                      className={`max-w-[92%] sm:max-w-[78%] rounded-2xl p-4 sm:p-5 text-xs sm:text-sm leading-relaxed ${
                        isUser
                          ? 'bg-slate-900 text-white shadow-sm rounded-tr-sm'
                          : 'bg-slate-50 text-slate-900 border border-slate-200 shadow-sm rounded-tl-sm'
                      }`}
                    >
                      <MessageContent content={msg.content} role={msg.role} conversationId={activeConversationId || undefined} messageId={msg.id} />
                      {!isUser && (
                        <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-slate-200 text-[11px] text-slate-500">
                          <button
                            type="button"
                            onClick={() => setContextInspectorMessageId(msg.id)}
                            className="inline-flex items-center space-x-1.5 text-slate-500 hover:text-emerald-700 transition-colors touch-target py-1 font-semibold"
                            title="Inspect memory context used for this response"
                            aria-label="Inspect context provenance"
                          >
                            <Brain className="w-3.5 h-3.5 text-emerald-600" />
                            <span>Context Inspector</span>
                          </button>
                          {Boolean(msg.metadata?.interrupted) && (
                            <span className="text-[10px] text-amber-600 italic font-mono">
                              (Stream interrupted)
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    {isUser && (
                      <div className="h-7 w-7 sm:h-8 sm:w-8 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 flex-shrink-0 text-xs mt-0.5 shadow-sm">
                        <User className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      </div>
                    )}
                  </div>
                );
              })}

              {/* In-Flight Streaming Assistant Bubble */}
              {isStreaming && (
                <div className="flex items-start space-x-2.5 sm:space-x-3.5 justify-start animate-in fade-in duration-150">
                  <div className="h-7 w-7 sm:h-8 sm:w-8 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-700 flex-shrink-0 text-xs mt-0.5 shadow-sm">
                    <Bot className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                  </div>
                  <div className="max-w-[92%] sm:max-w-[78%] rounded-2xl p-4 sm:p-5 text-xs sm:text-sm leading-relaxed bg-slate-50 text-slate-900 border border-slate-200 shadow-sm rounded-tl-sm">
                    {streamingContent ? (
                      <MessageContent content={streamingContent} role="assistant" conversationId={activeConversationId || undefined} />
                    ) : (
                      <span className="inline-flex items-center space-x-2 text-slate-500 text-xs animate-pulse">
                        <span className="font-semibold text-emerald-700">AUREN is thinking</span>
                        <span className="inline-block w-1.5 h-1.5 bg-emerald-500 rounded-full animate-bounce"></span>
                      </span>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {reconnectStatus && (
            <div className="p-3 sm:p-3.5 rounded-xl bg-amber-50 border border-amber-200 flex items-center space-x-2.5 text-xs text-amber-800 animate-pulse font-medium">
              <Loader2 className="h-4 w-4 animate-spin text-amber-600 flex-shrink-0" />
              <span>{reconnectStatus}</span>
            </div>
          )}

          {errorMessage && (
            <div className="p-3 sm:p-3.5 rounded-xl bg-rose-50 border border-rose-200 flex items-center justify-between text-xs text-rose-800">
              <div className="flex items-start space-x-2.5">
                <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5 text-rose-600" />
                <div>
                  <span className="font-bold">Error: </span>
                  <span>{errorMessage}</span>
                </div>
              </div>
              {pendingRetry ? (
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={isStreaming}
                  className="ml-2.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition flex-shrink-0 disabled:opacity-50 touch-target shadow-sm"
                  title="Retry failed message with identical idempotency key"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  <span>Retry</span>
                </button>
              ) : activeConversationId && messagesError ? (
                <button
                  type="button"
                  onClick={() => navigate({ to: '/chat' })}
                  className="ml-2.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded-lg text-slate-800 text-xs font-semibold touch-target"
                >
                  Return to Chat
                </button>
              ) : null}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Composer Bar */}
        <div className="p-2.5 sm:p-4 border-t border-slate-200 bg-white/95 backdrop-blur-md pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-xs">
          <form
            onSubmit={handleSendMessage}
            className="flex items-center gap-2 p-1.5 sm:p-2 bg-slate-50 border border-slate-200 rounded-2xl focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-500/20 transition-all shadow-inner"
          >
            <textarea
              rows={1}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              placeholder="Ask AUREN anything..."
              disabled={isStreaming}
              className="flex-1 bg-transparent border-0 outline-none px-3 py-1.5 text-xs sm:text-sm text-slate-900 placeholder-slate-400 focus:ring-0 resize-none min-h-[36px] max-h-[130px] leading-relaxed"
            />

            <div className="flex items-center flex-shrink-0 pr-1">
              {isStreaming ? (
                <button
                  type="button"
                  onClick={handleStopStreaming}
                  className="h-8 w-8 sm:h-9 sm:w-9 rounded-xl bg-rose-600 hover:bg-rose-500 text-white transition touch-target flex items-center justify-center shadow-md shadow-rose-600/30 cursor-pointer"
                  title="Stop generating"
                  aria-label="Stop generating"
                >
                  <Square className="h-3.5 w-3.5 fill-white" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!inputValue.trim()}
                  className={`h-8 w-8 sm:h-9 sm:w-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer ${
                    inputValue.trim()
                      ? 'bg-emerald-500 hover:bg-emerald-400 active:scale-95 text-white shadow-md shadow-emerald-500/30'
                      : 'bg-slate-200 text-slate-400 border border-slate-200'
                  }`}
                  title="Send message"
                  aria-label="Send message"
                >
                  <Send className="h-3.5 w-3.5 ml-0.5" />
                </button>
              )}
            </div>
          </form>

          <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-400 px-1 font-mono">
            <span className="hidden sm:inline">Enter to send &bull; Shift+Enter for newline</span>
            {inputValue.length > 500 && (
              <span className="ml-auto">{inputValue.length}/10000 characters</span>
            )}
          </div>
        </div>
      </section>

      {/* Lifecycle Modals */}
      {activeConv && (
        <>
          <RenameConversationModal
            isOpen={isRenameModalOpen}
            initialTitle={activeConv.title}
            onClose={() => setIsRenameModalOpen(false)}
            onRename={handleRenameConfirm}
          />
          <DeleteConversationModal
            isOpen={isDeleteModalOpen}
            conversationTitle={activeConv.title}
            onClose={() => setIsDeleteModalOpen(false)}
            onConfirmDelete={handleDeleteConfirm}
          />
        </>
      )}

      {/* Context Inspector Modal */}
      <ContextInspectorModal
        isOpen={Boolean(contextInspectorMessageId)}
        onClose={() => setContextInspectorMessageId(null)}
        conversationId={activeConversationId || undefined}
        messageId={contextInspectorMessageId || undefined}
        userId={user?.id}
      />

      {/* Auth Modal for Unauthenticated Users */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
      />
    </div>
  );
};
