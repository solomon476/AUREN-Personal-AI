/**
 * Persistent Chat & Streaming Conversational View for Phase 3A.
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
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
  RotateCcw 
} from 'lucide-react';
import { 
  Conversation, 
  ChatMessage, 
  listConversations, 
  createConversation, 
  getConversationMessages, 
  streamChat 
} from '../../api/chat';
import { useAuth } from '../../context/AuthContext';

export const ChatView: React.FC = () => {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pendingRetry, setPendingRetry] = useState<{
    message: string;
    conversationId?: string;
    idempotencyKey: string;
  } | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

  // Load conversations list
  const loadConversations = useCallback(async () => {
    if (!user) return;
    try {
      const data = await listConversations();
      setConversations(data);
      if (data.length > 0 && !activeConversationId) {
        setActiveConversationId(data[0].id);
      }
    } catch (err) {
      console.warn('Failed to load conversations:', err);
    }
  }, [user, activeConversationId]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // Load messages when active conversation changes
  useEffect(() => {
    if (!activeConversationId || !user) {
      setMessages([]);
      return;
    }

    let isMounted = true;
    setIsLoadingMessages(true);
    setErrorMessage(null);

    getConversationMessages(activeConversationId)
      .then((data) => {
        if (isMounted) {
          setMessages(data);
          setIsLoadingMessages(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setErrorMessage(err instanceof Error ? err.message : 'Could not load messages');
          setIsLoadingMessages(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [activeConversationId, user]);

  const handleNewConversation = async () => {
    if (isStreaming) return;
    try {
      const newConv = await createConversation('New Conversation');
      setConversations((prev) => [newConv, ...prev]);
      setActiveConversationId(newConv.id);
      setMessages([]);
      setErrorMessage(null);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to create conversation');
    }
  };

  const executeChatStream = async (
    messageText: string,
    conversationId: string | undefined,
    idempotencyKey: string,
  ) => {
    setIsStreaming(true);
    setStreamingContent('');
    setErrorMessage(null);
    abortControllerRef.current = new AbortController();

    try {
      await streamChat(
        messageText,
        conversationId,
        {
          onMetadata: (meta) => {
            if (!activeConversationId || activeConversationId !== meta.conversation_id) {
              setActiveConversationId(meta.conversation_id);
              loadConversations();
            }
          },
          onToken: (token) => {
            setStreamingContent((prev) => prev + token);
          },
          onDone: () => {
            setStreamingContent((finalText) => {
              const assistantMessage: ChatMessage = {
                id: `assistant-${Date.now()}`,
                conversation_id: activeConversationId || '',
                role: 'assistant',
                content: finalText,
                created_at: new Date().toISOString(),
              };
              setMessages((prev) => [...prev, assistantMessage]);
              return '';
            });
            setPendingRetry(null);
            setIsStreaming(false);
            loadConversations();
          },
          onError: (err) => {
            setErrorMessage(err);
            setPendingRetry({ message: messageText, conversationId, idempotencyKey });
            setIsStreaming(false);
          },
        },
        abortControllerRef.current.signal,
        idempotencyKey,
      );
    } catch (err) {
      if (!abortControllerRef.current?.signal.aborted) {
        const msg = err instanceof Error ? err.message : 'Streaming failed';
        setErrorMessage(msg);
        setPendingRetry({ message: messageText, conversationId, idempotencyKey });
      }
      setIsStreaming(false);
    }
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed || isStreaming) return;

    const idempotencyKey = `req-${crypto.randomUUID()}`;
    setInputValue('');

    // Optimistically append user message with stable idempotencyKey
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
    }
  };

  const activeConv = conversations.find((c) => c.id === activeConversationId);

  return (
    <div className="flex h-[calc(100vh-12rem)] min-h-[500px] bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl backdrop-blur">
      {/* Sidebar: Threads History */}
      <aside className="w-64 sm:w-72 bg-slate-950/80 border-r border-slate-800/80 flex flex-col flex-shrink-0">
        <div className="p-3 border-b border-slate-800">
          <button
            onClick={handleNewConversation}
            disabled={isStreaming}
            className="w-full flex items-center justify-center space-x-2 py-2 px-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-md shadow-indigo-600/20 transition"
          >
            <Plus className="h-4 w-4" />
            <span>New Conversation</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-500">
              No conversations yet. Start one above!
            </div>
          ) : (
            conversations.map((c) => {
              const isActive = c.id === activeConversationId;
              return (
                <button
                  key={c.id}
                  onClick={() => {
                    if (!isStreaming) setActiveConversationId(c.id);
                  }}
                  className={`w-full flex items-center space-x-2.5 px-3 py-2.5 rounded-lg text-left text-xs transition truncate ${
                    isActive
                      ? 'bg-indigo-950/60 border border-indigo-800/50 text-indigo-200'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  }`}
                >
                  <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 opacity-70" />
                  <span className="truncate flex-1 font-medium">{c.title}</span>
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
          <div className="flex items-center space-x-2">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            <h3 className="text-xs font-semibold text-white truncate max-w-md">
              {activeConv ? activeConv.title : 'New Dialogue'}
            </h3>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            SSE Stream &bull; Backend Verified
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
                      <div className="h-7 w-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400 flex-shrink-0 text-xs">
                        <Bot className="h-4 w-4" />
                      </div>
                    )}
                    <div
                      className={`max-w-[80%] sm:max-w-[70%] rounded-2xl p-3.5 text-xs sm:text-sm leading-relaxed whitespace-pre-wrap ${
                        isUser
                          ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20'
                          : 'bg-slate-800/80 text-slate-200 border border-slate-700/60'
                      }`}
                    >
                      {msg.content}
                      {!isUser && Boolean(msg.metadata?.interrupted) && (
                        <div className="mt-1.5 text-[10px] text-amber-400/90 italic font-mono">
                          (Stream interrupted)
                        </div>
                      )}
                    </div>
                    {isUser && (
                      <div className="h-7 w-7 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 flex-shrink-0 text-xs">
                        <User className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                );
              })}

              {/* In-Flight Streaming Assistant Bubble */}
              {isStreaming && (
                <div className="flex items-start space-x-3 justify-start animate-in fade-in duration-150">
                  <div className="h-7 w-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400 flex-shrink-0 text-xs">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="max-w-[80%] sm:max-w-[70%] rounded-2xl p-3.5 text-xs sm:text-sm leading-relaxed bg-slate-800/80 text-slate-200 border border-slate-700/60 whitespace-pre-wrap">
                    {streamingContent || (
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

          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/50 flex items-center justify-between text-xs text-rose-300">
              <div className="flex items-start space-x-2">
                <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5 text-rose-400" />
                <div>
                  <span className="font-semibold">Error: </span>
                  <span>{errorMessage}</span>
                </div>
              </div>
              {pendingRetry && (
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
              )}
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
                >
                  <Square className="h-4 w-4 fill-white" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!inputValue.trim()}
                  className="p-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white rounded-lg transition shadow-md shadow-indigo-600/20"
                  title="Send message"
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
    </div>
  );
};

