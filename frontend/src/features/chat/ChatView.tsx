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
  X,
  Mic,
  Check,
  Volume2,
  FileText,
  Download,
} from 'lucide-react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { API_BASE_URL } from '../../api/client';
import { useSafeSearch } from '../../hooks/useSafeSearch';
import {
  AttachmentItem,
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

  // Keep-warm ping to eliminate Railway cold starts while app is open
  useEffect(() => {
    const pingBackend = () => {
      fetch(`${API_BASE_URL}/health`).catch(() => {});
    };
    pingBackend();
    const pingInterval = setInterval(pingBackend, 4 * 60 * 1000);
    return () => clearInterval(pingInterval);
  }, []);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pendingRetry, setPendingRetry] = useState<{
    message: string;
    conversationId?: string;
    idempotencyKey: string;
    attachments?: AttachmentItem[];
  } | null>(null);

  // Image Attachments State
  const [selectedImages, setSelectedImages] = useState<Array<{
    name: string;
    size: number;
    previewUrl: string;
    dataUrl: string;
  }>>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Document & File Attachments State (PDF, DOCX, TXT, CSV, etc.)
  const [selectedDocs, setSelectedDocs] = useState<Array<{
    name: string;
    size: number;
    dataUrl: string;
    type: string;
  }>>([]);
  const [isAttachMenuOpen, setIsAttachMenuOpen] = useState(false);
  const docInputRef = useRef<HTMLInputElement | null>(null);

  // Voice Note Recording State
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [recordedAudioUrl, setRecordedAudioUrl] = useState<string | null>(null);
  const [recordedAudioBase64, setRecordedAudioBase64] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const recordingTimerRef = useRef<any>(null);
  const speechRecognitionRef = useRef<any>(null);

  // Format seconds to mm:ss
  const formatDuration = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  // Image Selection Handler
  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    Array.from(files).forEach((file) => {
      if (!file.type.startsWith('image/')) return;
      const previewUrl = URL.createObjectURL(file);
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          setSelectedImages((prev) => [
            ...prev,
            {
              name: file.name,
              size: file.size,
              previewUrl,
              dataUrl: reader.result as string,
            },
          ]);
        }
      };
      reader.readAsDataURL(file);
    });

    e.target.value = '';
  };

  const handleRemoveImage = (index: number) => {
    setSelectedImages((prev) => {
      const target = prev[index];
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return prev.filter((_, i) => i !== index);
    });
  };

  // Document & File Selection Handler
  const handleDocumentSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    Array.from(files).forEach((file) => {
      // 20MB safety limit for client-side base64
      if (file.size > 20 * 1024 * 1024) {
        setErrorMessage(`File "${file.name}" exceeds 20MB limit.`);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          setSelectedDocs((prev) => [
            ...prev,
            {
              name: file.name,
              size: file.size,
              dataUrl: reader.result as string,
              type: file.type || 'application/octet-stream',
            },
          ]);
        }
      };
      reader.readAsDataURL(file);
    });

    e.target.value = '';
    setIsAttachMenuOpen(false);
  };

  const handleRemoveDocument = (index: number) => {
    setSelectedDocs((prev) => prev.filter((_, i) => i !== index));
  };

  // Voice Recording Handlers
  const startVoiceRecording = async () => {
    if (isStreaming) return;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setErrorMessage('Voice recording is not supported in this browser environment.');
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;

      let mimeType = '';
      if (typeof MediaRecorder !== 'undefined') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
          mimeType = 'audio/webm;codecs=opus';
        } else if (MediaRecorder.isTypeSupported('audio/webm')) {
          mimeType = 'audio/webm';
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = 'audio/mp4';
        }
      }

      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      const chunks: BlobPart[] = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onstop = () => {
        const audioBlob = new Blob(chunks, { type: mimeType || 'audio/webm' });
        const audioUrl = URL.createObjectURL(audioBlob);
        setRecordedAudioUrl(audioUrl);

        const reader = new FileReader();
        reader.onloadend = () => {
          if (typeof reader.result === 'string') {
            setRecordedAudioBase64(reader.result);
          }
        };
        reader.readAsDataURL(audioBlob);

        // Stop tracks for privacy
        if (audioStreamRef.current) {
          audioStreamRef.current.getTracks().forEach((track) => track.stop());
          audioStreamRef.current = null;
        }
      };

      recorder.start(250);
      setIsRecording(true);
      setRecordingDuration(0);

      // Start duration timer
      recordingTimerRef.current = setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);

      // Web Speech API real-time speech-to-text
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        try {
          const recognition = new SpeechRecognition();
          recognition.continuous = true;
          recognition.interimResults = true;
          recognition.lang = 'en-US';
          recognition.onresult = (event: any) => {
            let transcriptText = '';
            for (let i = 0; i < event.results.length; i++) {
              transcriptText += event.results[i][0].transcript;
            }
            if (transcriptText) {
              setInputValue((prev) => {
                const base = prev.trim();
                return base ? `${base} ${transcriptText.trim()}` : transcriptText.trim();
              });
            }
          };
          recognition.start();
          speechRecognitionRef.current = recognition;
        } catch (recErr) {
          console.warn('Speech recognition start failed (non-critical):', recErr);
        }
      }
    } catch (err: any) {
      console.error('Microphone access failed:', err);
      setErrorMessage(
        err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError'
          ? 'Microphone permission denied. Please allow microphone access in your browser settings.'
          : 'Unable to access microphone. Please check audio device settings.'
      );
      setIsRecording(false);
    }
  };

  const stopVoiceRecording = () => {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (speechRecognitionRef.current) {
      try {
        speechRecognitionRef.current.stop();
      } catch {
        // Recognition already stopped
      }
      speechRecognitionRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  const discardVoiceRecording = () => {
    if (isRecording) {
      stopVoiceRecording();
    }
    if (recordedAudioUrl) {
      URL.revokeObjectURL(recordedAudioUrl);
    }
    setRecordedAudioUrl(null);
    setRecordedAudioBase64(null);
    setRecordingDuration(0);
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop());
      audioStreamRef.current = null;
    }
  };

  // Cleanup audio tracks and timer on unmount
  useEffect(() => {
    return () => {
      if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (speechRecognitionRef.current) {
        try {
          speechRecognitionRef.current.stop();
        } catch {}
      }
    };
  }, []);

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
    if (isAtBottomRef.current && (messages.length > 0 || streamingContent)) {
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
   * Resilient SSE streaming with fast failover and single bounded reconnect.
   */
  const MAX_RETRIES = 1;
  const executeChatStream = async (
    messageText: string,
    targetConversationId: string | undefined,
    idempotencyKey: string,
    attempt = 0,
    attachmentsToSend?: AttachmentItem[],
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
        attachmentsToSend,
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
          return executeChatStream(messageText, targetConversationId, idempotencyKey, nextAttempt, attachmentsToSend);
        }
      }

      setErrorMessage(errMsg || 'Streaming failed');
      setReconnectStatus(null);
      setPendingRetry({ message: messageText, conversationId: targetConversationId, idempotencyKey, attachments: attachmentsToSend });
      setIsStreaming(false);
    }
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = inputValue.trim();
    const hasAttachments = selectedImages.length > 0 || selectedDocs.length > 0 || Boolean(recordedAudioBase64);
    if ((!trimmed && !hasAttachments) || isStreaming) return;

    if (!user) {
      setIsAuthModalOpen(true);
      return;
    }

    const idempotencyKey = `req-${crypto.randomUUID()}`;
    const attachmentsToSend: AttachmentItem[] = [
      ...selectedImages.map((img) => ({
        type: 'image' as const,
        url: img.dataUrl,
        name: img.name,
        size: img.size,
      })),
      ...selectedDocs.map((doc) => ({
        type: 'document' as const,
        url: doc.dataUrl,
        name: doc.name,
        size: doc.size,
      })),
      ...(recordedAudioBase64
        ? [
            {
              type: 'audio' as const,
              url: recordedAudioBase64,
              duration: recordingDuration,
            },
          ]
        : []),
    ];

    const messageText =
      trimmed ||
      (selectedDocs.length > 0
        ? `Please examine the attached document(s): ${selectedDocs.map((d) => d.name).join(', ')}`
        : recordedAudioBase64
        ? 'Voice message note'
        : 'Please analyze the attached image.');

    setInputValue('');
    setSelectedImages([]);
    setSelectedDocs([]);
    setRecordedAudioUrl(null);
    setRecordedAudioBase64(null);
    setRecordingDuration(0);

    const tempUserMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: activeConversationId || '',
      role: 'user',
      content:
        trimmed ||
        (selectedDocs.length > 0
          ? `📄 Attached ${selectedDocs.length} file(s)`
          : recordedAudioBase64
          ? '🎤 Voice message'
          : '🖼️ Attached image'),
      idempotency_key: idempotencyKey,
      metadata: attachmentsToSend.length > 0 ? { attachments: attachmentsToSend } : undefined,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    await executeChatStream(
      messageText,
      activeConversationId || undefined,
      idempotencyKey,
      0,
      attachmentsToSend,
    );
  };

  const handleRetry = async () => {
    if (!pendingRetry || isStreaming) return;
    const retryKey = `req-${crypto.randomUUID()}`;
    await executeChatStream(
      pendingRetry.message,
      pendingRetry.conversationId,
      retryKey,
      0,
      pendingRetry.attachments,
    );
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
            <div className="flex-1 min-h-[220px] flex flex-col items-center justify-center text-center p-4 sm:p-6 space-y-4 sm:space-y-5">
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
                      {/* Attachments rendering (Images, Documents & Voice Notes) */}
                      {msg.metadata?.attachments && Array.isArray(msg.metadata.attachments) && msg.metadata.attachments.length > 0 && (
                        <div className="space-y-2 mb-2.5">
                          {msg.metadata.attachments.map((att: any, attIdx: number) => (
                            <div key={attIdx}>
                              {att.type === 'image' && (
                                <div className="rounded-xl overflow-hidden border border-slate-200/80 bg-white/50 inline-block max-w-full">
                                  <img
                                    src={att.url}
                                    alt={att.name || 'Attached image'}
                                    className="max-h-64 max-w-full rounded-xl object-contain cursor-pointer hover:opacity-95 transition"
                                    onClick={() => window.open(att.url, '_blank')}
                                  />
                                  {att.name && (
                                    <div className="px-2 py-1 text-[10px] text-slate-500 truncate max-w-xs">
                                      {att.name}
                                    </div>
                                  )}
                                </div>
                              )}
                              {(att.type === 'document' || att.type === 'file') && (
                                <div className="p-2.5 rounded-xl bg-white/90 border border-slate-200/90 shadow-2xs flex items-center justify-between gap-3 max-w-sm">
                                  <div className="flex items-center space-x-2.5 min-w-0 flex-1">
                                    <div className="h-8 w-8 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center flex-shrink-0">
                                      <FileText className="w-4 h-4" />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                      <p className="text-xs font-semibold text-slate-800 truncate" title={att.name || 'Document'}>
                                        {att.name || 'Attached Document'}
                                      </p>
                                      <p className="text-[10px] text-slate-500 font-mono">
                                        {att.size ? (att.size > 1024 * 1024 ? `${(att.size / (1024 * 1024)).toFixed(1)} MB` : `${Math.round(att.size / 1024)} KB`) : 'Document file'}
                                      </p>
                                    </div>
                                  </div>
                                  {att.url && (
                                    <a
                                      href={att.url}
                                      download={att.name || 'document'}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition flex-shrink-0"
                                      title="Download / View document"
                                    >
                                      <Download className="w-3.5 h-3.5" />
                                    </a>
                                  )}
                                </div>
                              )}
                              {att.type === 'audio' && (
                                <div className="p-2 rounded-xl bg-white/90 border border-slate-200 shadow-xs flex items-center space-x-2 max-w-xs">
                                  <Volume2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                                  <audio controls src={att.url} className="w-full h-8" />
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Content rendering */}
                      {isUser ? (
                        <MessageContent content={msg.content} role={msg.role} conversationId={activeConversationId || undefined} messageId={msg.id} />
                      ) : (
                        (() => {
                          const hasContent = Boolean(msg.content && msg.content.trim());
                          if (!hasContent) {
                            return (
                              <div className="flex flex-col space-y-2 py-0.5">
                                <div className="flex items-center justify-between text-xs text-amber-800 bg-amber-50/90 border border-amber-200/80 rounded-xl p-3">
                                  <div className="flex items-center space-x-2">
                                    <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                                    <span className="font-medium">Response could not be retrieved.</span>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const prevUser = messages.slice(0, index).reverse().find((m) => m.role === 'user');
                                      if (prevUser?.content) {
                                        executeChatStream(
                                          prevUser.content,
                                          activeConversationId || undefined,
                                          `retry-${Date.now()}`,
                                          0,
                                        );
                                      }
                                    }}
                                    className="ml-3 text-emerald-700 hover:text-emerald-800 font-semibold underline text-xs flex-shrink-0 cursor-pointer"
                                  >
                                    Retry
                                  </button>
                                </div>
                              </div>
                            );
                          }
                          return (
                            <>
                              <MessageContent content={msg.content} role={msg.role} conversationId={activeConversationId || undefined} messageId={msg.id} />
                              {Boolean(msg.metadata?.interrupted) && (
                                <div className="mt-2 text-[10px] text-amber-600 italic font-mono">
                                  (Stream interrupted)
                                </div>
                              )}
                            </>
                          );
                        })()
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
                      <div className="flex flex-col space-y-1">
                        <span className="inline-flex items-center space-x-2 text-slate-600 text-xs font-medium">
                          <span className="inline-block w-2 h-2 bg-emerald-500 rounded-full animate-ping"></span>
                          <span className="font-semibold text-emerald-700">AUREN is thinking...</span>
                        </span>
                      </div>
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
          {/* Image Previews Strip */}
          {selectedImages.length > 0 && (
            <div className="flex items-center gap-2 mb-2.5 overflow-x-auto pb-1 scrollbar-thin">
              {selectedImages.map((img, idx) => (
                <div
                  key={idx}
                  className="relative group flex items-center gap-2 p-1.5 bg-slate-100 border border-slate-200 rounded-xl flex-shrink-0 shadow-xs"
                >
                  <img
                    src={img.previewUrl}
                    alt={img.name}
                    className="h-10 w-10 object-cover rounded-lg border border-slate-200"
                  />
                  <div className="text-[11px] max-w-[130px] truncate">
                    <p className="font-semibold text-slate-800 truncate">{img.name}</p>
                    <p className="text-[10px] text-slate-500 font-mono">
                      {(img.size / 1024).toFixed(0)} KB
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveImage(idx)}
                    className="p-1 rounded-full text-slate-400 hover:text-rose-600 hover:bg-white transition cursor-pointer"
                    title="Remove image"
                    aria-label="Remove image"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Document Previews Strip */}
          {selectedDocs.length > 0 && (
            <div className="flex items-center gap-2 mb-2.5 overflow-x-auto pb-1 scrollbar-thin">
              {selectedDocs.map((doc, idx) => (
                <div
                  key={idx}
                  className="relative group flex items-center gap-2 p-2 bg-indigo-50/80 border border-indigo-200/80 rounded-xl flex-shrink-0 shadow-2xs"
                >
                  <div className="h-8 w-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center flex-shrink-0">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div className="text-[11px] max-w-[140px] truncate">
                    <p className="font-semibold text-slate-800 truncate" title={doc.name}>{doc.name}</p>
                    <p className="text-[10px] text-slate-500 font-mono">
                      {doc.size > 1024 * 1024
                        ? `${(doc.size / (1024 * 1024)).toFixed(1)} MB`
                        : `${Math.round(doc.size / 1024)} KB`}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveDocument(idx)}
                    className="p-1 rounded-full text-slate-400 hover:text-rose-600 hover:bg-white transition cursor-pointer"
                    title="Remove document"
                    aria-label="Remove document"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Recorded Audio Preview Strip */}
          {recordedAudioUrl && !isRecording && (
            <div className="flex items-center justify-between gap-3 mb-2.5 p-2.5 bg-emerald-50/90 border border-emerald-200 rounded-2xl shadow-xs">
              <div className="flex items-center space-x-2 flex-1 min-w-0">
                <div className="h-8 w-8 rounded-xl bg-emerald-600 text-white flex items-center justify-center flex-shrink-0 shadow-sm">
                  <Mic className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-emerald-900">Voice Note Preview</p>
                  <p className="text-[10px] text-emerald-700 font-mono">Duration: {formatDuration(recordingDuration)}</p>
                </div>
                <audio src={recordedAudioUrl} controls className="h-8 max-w-[200px] xs:max-w-[260px]" />
              </div>
              <button
                type="button"
                onClick={discardVoiceRecording}
                className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition touch-target flex-shrink-0 cursor-pointer"
                title="Discard recording"
                aria-label="Discard recording"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Active Voice Recording Bar */}
          {isRecording ? (
            <div className="flex items-center justify-between gap-3 p-2.5 bg-rose-50 border border-rose-200 rounded-2xl animate-pulse shadow-sm">
              <div className="flex items-center space-x-2.5">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-600"></span>
                </span>
                <span className="text-xs font-bold text-rose-900">Recording voice note...</span>
                <span className="text-xs font-mono font-bold text-rose-950 bg-white/90 px-2 py-0.5 rounded-lg border border-rose-200 shadow-2xs">
                  {formatDuration(recordingDuration)}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={discardVoiceRecording}
                  className="p-2 text-slate-600 hover:text-rose-600 hover:bg-white rounded-xl transition touch-target cursor-pointer"
                  title="Cancel recording"
                  aria-label="Cancel recording"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={stopVoiceRecording}
                  className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold flex items-center space-x-1.5 transition touch-target shadow-sm cursor-pointer"
                  title="Done recording"
                  aria-label="Finish recording"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Done</span>
                </button>
              </div>
            </div>
          ) : (
            <form
              onSubmit={handleSendMessage}
              className="flex items-center gap-1.5 sm:gap-2 p-1.5 sm:p-2 bg-white border border-slate-200/90 rounded-2xl focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-500/20 transition-all shadow-sm relative"
            >
              {/* Hidden File Input for Image Attachments */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={handleImageSelect}
              />

              {/* Hidden File Input for Document Attachments */}
              <input
                ref={docInputRef}
                type="file"
                accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.json,application/pdf,text/*"
                multiple
                className="hidden"
                onChange={handleDocumentSelect}
              />

              {/* Attachments Dropdown Menu Button */}
              <div className="relative flex-shrink-0">
                <button
                  type="button"
                  onClick={() => setIsAttachMenuOpen((prev) => !prev)}
                  disabled={isStreaming}
                  className={`h-8 w-8 sm:h-9 sm:w-9 rounded-xl flex items-center justify-center transition touch-target flex-shrink-0 cursor-pointer disabled:opacity-50 ${
                    isAttachMenuOpen
                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                      : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                  title="Attach photo or document"
                  aria-label="Attach image or document"
                >
                  <Plus className={`h-4 w-4 sm:h-4.5 sm:w-4.5 transition-transform duration-200 ${isAttachMenuOpen ? 'rotate-45' : ''}`} />
                </button>

                {isAttachMenuOpen && (
                  <div className="absolute bottom-full left-0 mb-2 w-56 bg-white rounded-2xl shadow-xl border border-slate-200/90 p-1.5 z-50 space-y-1 animate-in fade-in duration-150">
                    <button
                      type="button"
                      onClick={() => {
                        setIsAttachMenuOpen(false);
                        fileInputRef.current?.click();
                      }}
                      className="w-full flex items-center space-x-2.5 px-3 py-2 rounded-xl text-left text-xs font-semibold text-slate-700 hover:text-emerald-700 hover:bg-emerald-50 transition cursor-pointer"
                    >
                      <span className="p-1.5 rounded-lg bg-emerald-100 text-emerald-700">
                        <Sparkles className="w-3.5 h-3.5" />
                      </span>
                      <span>Photo / Image</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setIsAttachMenuOpen(false);
                        docInputRef.current?.click();
                      }}
                      className="w-full flex items-center space-x-2.5 px-3 py-2 rounded-xl text-left text-xs font-semibold text-slate-700 hover:text-indigo-700 hover:bg-indigo-50 transition cursor-pointer"
                    >
                      <span className="p-1.5 rounded-lg bg-indigo-100 text-indigo-700">
                        <FileText className="w-3.5 h-3.5" />
                      </span>
                      <span>Document / PDF</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Voice Note Button */}
              <button
                type="button"
                onClick={startVoiceRecording}
                disabled={isStreaming}
                className="h-8 w-8 sm:h-9 sm:w-9 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition touch-target flex-shrink-0 cursor-pointer disabled:opacity-50"
                title="Record voice note"
                aria-label="Record voice note"
              >
                <Mic className="h-4 w-4 sm:h-4.5 sm:w-4.5" />
              </button>

              {/* Text Area */}
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
                placeholder={
                  selectedDocs.length > 0
                    ? 'Add a message about this document...'
                    : selectedImages.length > 0
                    ? 'Add a message about this image...'
                    : 'Ask AUREN anything...'
                }
                disabled={isStreaming}
                className="flex-1 bg-transparent border-0 outline-none px-2 sm:px-3 py-1.5 text-xs sm:text-sm text-slate-900 placeholder-slate-400 focus:ring-0 resize-none min-h-[36px] max-h-[130px] leading-relaxed"
              />

              {/* Send / Stop Generation Button */}
              <div className="flex items-center flex-shrink-0 pr-0.5">
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
                    disabled={!inputValue.trim() && selectedImages.length === 0 && selectedDocs.length === 0 && !recordedAudioBase64}
                    className={`h-8 w-8 sm:h-9 sm:w-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer ${
                      inputValue.trim() || selectedImages.length > 0 || selectedDocs.length > 0 || recordedAudioBase64
                        ? 'bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white shadow-md shadow-emerald-600/25'
                        : 'bg-slate-100 text-slate-400 border border-slate-200/80 hover:bg-slate-200/50'
                    }`}
                    title="Send message"
                    aria-label="Send message"
                  >
                    <Send className="h-3.5 w-3.5 ml-0.5" />
                  </button>
                )}
              </div>
            </form>
          )}

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
