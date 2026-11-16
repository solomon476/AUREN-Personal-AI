/**
 * Persistent Chat & Streaming Conversational View.
 * Enhanced with Rich Markdown & Code Rendering, Conversation Rename/Delete Lifecycle,
 * and Resilient SSE Reconnection with Exponential Backoff.
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
  Trash2
} from 'lucide-react';
import { useNavigate, useParams } from '@tanstack/react-router';
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

  // Local State for interactive stream accumulation, modals, and input
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [reconnectStatus, setReconnectStatus] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pendingRetry, setPendingRetry] = useState<{
    message: string;
    conversationId?: string;
    idempotencyKey: string;
  } | null>(null);

  // Modals for conversation lifecycle
  const [isRenameModalOpen, setIsRenameModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, reconnectStatus]);

  // Sync server-cached messages into local state when conversation loads
  useEffect(() => {
    if (fetchedMessages) {
      setMessages(fetchedMessages);
      setErrorMessage(null);
    } else if (!activeConversationId) {
      setMessages([]);
    }
  }, [fetchedMessages, activeConversationId]);

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
    try {
      const newConv = await createConversationMutation.mutateAsync('New Conversation');
      setMessages([]);
      setErrorMessage(null);
      navigate({ to: '/chat/$conversationId', params: { conversationId: newConv.id } });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to create conversation');
    }
  };

  const handleSelectConversation = (id: string) => {
    if (isStreaming) return;
    setErrorMessage(null);
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
        errMsg.includes('conflicting request parameters');

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

  return (
    <div className="flex h-[calc(100vh-5rem)] min-h-[500px] bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl backdrop-blur">
      {/* Sidebar: Threads History */}
      <aside className="w-64 sm:w-72 bg-slate-950/80 border-r border-slate-800/80 flex flex-col flex-shrink-0">
        <div className="p-3 border-b border-slate-800">
          <button
            onClick={handleNewConversation}
            disabled={isStreaming || createConversationMutation.isPending}
            className="w-full flex items-center justify-center space-x-2 py-2 px-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-md shadow-indigo-600/20 transition"
          >
            <Plus className="h-4 w-4" />
            <span>New Conversation</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {isLoadingConversations ? (
            <div className="p-4 text-center text-xs text-slate-500 flex items-center justify-center space-x-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
              <span>Loading threads...</span>
            </div>
          ) : conversations.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-500">
              No conversations yet. Start one above!
            </div>
          ) : (
            conversations.map((c) => {
              const isActive = c.id === activeConversationId;
              return (
                <button
                  key={c.id}
                  onClick={() => handleSelectConversation(c.id)}
                  className={`w-full flex items-center space-x-2.5 px-3 py-2.5 rounded-lg text-left text-xs transition truncate ${
                    isActive
                      ? 'bg-indigo-950/60 border border-indigo-800/50 text-indigo-200'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  }`}
                >
                  <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 opacity-70" />
                  <span className="truncate flex-1 font-medium">{c.title}</span>
                  {typeof c.message_count === 'number' && c.message_count > 0 && (
                    <span className="text-[10px] text-slate-500 font-mono">
                      {c.message_count}
                    </span>
                  )}
                </button>
              );
            })
          )}
        </div>
      </aside>

      {/* Main Chat Workspace */}
      <section className="flex-1 flex flex-col bg-slate-900/40">
        {/* Active Thread Header */}
        <div className="h-12 border-b border-slate-800 px-4 flex items-center justify-between bg-slate-950/40">
          <div className="flex items-center space-x-2 min-w-0">
            <Sparkles className="h-4 w-4 text-indigo-400 flex-shrink-0" />
            <h3 className="text-xs font-semibold text-white truncate max-w-xs sm:max-w-md">
              {activeConv ? activeConv.title : 'New Dialogue'}
            </h3>
            {activeConv && (
              <div className="flex items-center space-x-1 pl-1">
                <button
                  onClick={() => setIsRenameModalOpen(true)}
                  className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition"
                  title="Rename conversation"
                  aria-label="Rename conversation"
                >
                  <Edit2 className="h-3 w-3" />
                </button>
                <button
                  onClick={() => setIsDeleteModalOpen(true)}
                  className="p-1 rounded-md text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition"
                  title="Delete conversation"
                  aria-label="Delete conversation"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            )}
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 hidden sm:inline-block">
            SSE Stream &bull; Markdown &bull; KaTeX
          </span>
        </div>

        {/* Message Stream Display */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
          {isLoadingMessages ? (
            <div className="h-full flex items-center justify-center text-slate-400 text-xs space-x-2">
              <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
              <span>Loading messages...</span>
            </div>
          ) : messages.length === 0 && !streamingContent ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-3">
              <div className="h-12 w-12 rounded-2xl bg-indigo-950/60 border border-indigo-800/50 flex items-center justify-center text-indigo-400 shadow-xl">
                <Bot className="h-6 w-6" />
              </div>
              <h4 className="text-base font-bold text-white">AUREN Personal AI Assistant</h4>
              <p className="text-xs text-slate-400 max-w-sm leading-relaxed">
                Ready to assist. Your dialogues are saved privately to your account with strict ownership enforcement.
              </p>
            </div>
          ) : (
            <>
              {messages.map((msg, index) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={msg.id || index}
                    className={`flex items-start space-x-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <div className="h-7 w-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400 flex-shrink-0 text-xs mt-1">
                        <Bot className="h-4 w-4" />
                      </div>
                    )}
                    <div
                      className={`max-w-[85%] sm:max-w-[75%] rounded-2xl p-3.5 text-xs sm:text-sm leading-relaxed ${
                        isUser
                          ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20'
                          : 'bg-slate-800/80 text-slate-200 border border-slate-700/60'
                      }`}
                    >
                      <MessageContent content={msg.content} role={msg.role} />
                      {!isUser && Boolean(msg.metadata?.interrupted) && (
                        <div className="mt-1.5 text-[10px] text-amber-400/90 italic font-mono">
                          (Stream interrupted)
                        </div>
                      )}
                    </div>
                    {isUser && (
                      <div className="h-7 w-7 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 flex-shrink-0 text-xs mt-1">
                        <User className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                );
              })}

              {/* In-Flight Streaming Assistant Bubble */}
              {isStreaming && (
                <div className="flex items-start space-x-3 justify-start animate-in fade-in duration-150">
                  <div className="h-7 w-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400 flex-shrink-0 text-xs mt-1">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl p-3.5 text-xs sm:text-sm leading-relaxed bg-slate-800/80 text-slate-200 border border-slate-700/60">
                    {streamingContent ? (
                      <MessageContent content={streamingContent} role="assistant" />
                    ) : (
                      <span className="inline-flex items-center space-x-1.5 text-slate-400 text-xs animate-pulse">
                        <span>AUREN is thinking</span>
                        <span className="inline-block w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce"></span>
                      </span>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {reconnectStatus && (
            <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-800/50 flex items-center space-x-2 text-xs text-amber-300 animate-pulse">
              <Loader2 className="h-4 w-4 animate-spin text-amber-400 flex-shrink-0" />
              <span>{reconnectStatus}</span>
            </div>
          )}

          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/50 flex items-center justify-between text-xs text-rose-300">
              <div className="flex items-start space-x-2">
                <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5 text-rose-400" />
                <div>
                  <span className="font-semibold">Error: </span>
                  <span>{errorMessage}</span>
                </div>
              </div>
              {pendingRetry ? (
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={isStreaming}
                  className="ml-3 px-3 py-1 bg-rose-900/60 hover:bg-rose-800/80 border border-rose-700/60 rounded-lg text-rose-200 text-xs font-semibold flex items-center space-x-1.5 transition flex-shrink-0 disabled:opacity-50"
                  title="Retry failed message with identical idempotency key"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  <span>Retry</span>
                </button>
              ) : activeConversationId && messagesError ? (
                <button
                  type="button"
                  onClick={() => navigate({ to: '/chat' })}
                  className="ml-3 px-3 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-200 text-xs font-medium"
                >
                  Return to Chat
                </button>
              ) : null}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Composer Bar */}
        <div className="p-3 sm:p-4 border-t border-slate-800 bg-slate-950/60">
          <form onSubmit={handleSendMessage} className="relative flex items-center">
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
              placeholder="Ask AUREN anything... (Enter to send, Shift+Enter for newline)"
              disabled={isStreaming}
              className="w-full resize-none py-2.5 pl-3.5 pr-20 bg-slate-900 border border-slate-800 rounded-xl text-xs sm:text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition disabled:opacity-50"
            />

            <div className="absolute right-2 flex items-center space-x-1.5">
              {isStreaming ? (
                <button
                  type="button"
                  onClick={handleStopStreaming}
                  className="p-1.5 bg-rose-600 hover:bg-rose-500 text-white rounded-lg transition"
                  title="Stop generating"
                  aria-label="Stop generating"
                >
                  <Square className="h-4 w-4 fill-white" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!inputValue.trim()}
                  className="p-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white rounded-lg transition shadow-md shadow-indigo-600/20"
                  title="Send message"
                  aria-label="Send message"
                >
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>
          </form>

          <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-500 px-1">
            <span>Enter to send &bull; Shift+Enter for newline</span>
            <span>{inputValue.length}/10000 characters</span>
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
    </div>
  );
};
