/**
 * Private Journal and Reflection Feature View.
 * Implements distraction-free writing, cryptographic consent isolation guarantees,
 * mood tracking, reflection prompts, and chronological history browsing.
 */

import React, { useState } from 'react';
import {
  BookOpen,
  Plus,
  Search,
  Calendar,
  Lock,
  Sparkles,
  Save,
  Trash2,
  Edit3,
  Tag,
  CheckCircle2,
  ChevronRight,
  Smile,
  Eye,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  useCreateJournalEntry,
  useDeleteJournalEntry,
  useJournalEntries,
  useUpdateJournalEntry,
} from '../../hooks/useJournal';
import { JournalEntry } from '../../api/journal';
import { MessageContent } from '../../components/chat/MessageContent';

const REFLECTION_PROMPTS = [
  'What was the single most impactful decision or achievement today?',
  'What gave you unexpected clarity or energy today?',
  'What is a core assumption you are currently testing or questioning?',
  'What is creating subtle friction or distraction right now, and how can you remove it?',
  'What are you grateful for in this moment of your personal journey?',
];

const MOOD_OPTIONS = [
  { value: 'focused', label: 'Focused', color: 'text-indigo-400 bg-indigo-950/60 border-indigo-800/40' },
  { value: 'energized', label: 'Energized', color: 'text-emerald-400 bg-emerald-950/60 border-emerald-800/40' },
  { value: 'calm', label: 'Calm', color: 'text-sky-400 bg-sky-950/60 border-sky-800/40' },
  { value: 'reflective', label: 'Reflective', color: 'text-purple-400 bg-purple-950/60 border-purple-800/40' },
  { value: 'tired', label: 'Tired', color: 'text-amber-400 bg-amber-950/60 border-amber-800/40' },
  { value: 'overwhelmed', label: 'Overwhelmed', color: 'text-rose-400 bg-rose-950/60 border-rose-800/40' },
];

export const JournalView: React.FC = () => {
  const { user } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMood, setSelectedMood] = useState<string>('');

  // Active editing or viewing entry
  const [selectedEntry, setSelectedEntry] = useState<JournalEntry | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editorTab, setEditorTab] = useState<'write' | 'preview'>('write');
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [mood, setMood] = useState('reflective');
  const [tagsInput, setTagsInput] = useState('');
  const [entryDate, setEntryDate] = useState(new Date().toISOString().split('T')[0]);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Queries and mutations
  const { data: journalData, isLoading, error } = useJournalEntries({
    query: searchQuery || undefined,
    mood: selectedMood || undefined,
    page: 1,
    page_size: 50,
  }, user?.id);

  const createMutation = useCreateJournalEntry(user?.id);
  const updateMutation = useUpdateJournalEntry(user?.id);
  const deleteMutation = useDeleteJournalEntry(user?.id);

  const handleOpenNewEntry = (initialPrompt?: string) => {
    setSelectedEntry(null);
    setEditingEntryId(null);
    setTitle('');
    setContent(initialPrompt ? `> **Prompt:** ${initialPrompt}\n\n` : '');
    setMood('reflective');
    setTagsInput('');
    setEntryDate(new Date().toISOString().split('T')[0]);
    setIsEditing(true);
    setEditorTab('write');
    setStatusMessage(null);
  };

  const handleSelectEntry = (entry: JournalEntry) => {
    setSelectedEntry(entry);
    setIsEditing(false);
    setStatusMessage(null);
  };

  const handleStartEdit = (entry: JournalEntry) => {
    setSelectedEntry(entry);
    setEditingEntryId(entry.id);
    setTitle(entry.title || '');
    setContent(entry.content);
    setMood(entry.mood || 'reflective');
    setTagsInput(entry.tags ? entry.tags.join(', ') : '');
    setEntryDate(entry.entry_date || new Date().toISOString().split('T')[0]);
    setIsEditing(true);
    setEditorTab('write');
    setStatusMessage(null);
  };

  const handleSaveEntry = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;

    const parsedTags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      let saved: JournalEntry;
      if (editingEntryId) {
        saved = await updateMutation.mutateAsync({
          entryId: editingEntryId,
          payload: {
            title: title.trim() || undefined,
            content: content.trim(),
            mood,
            tags: parsedTags,
            entry_date: entryDate,
          },
        });
        setStatusMessage('Reflection updated securely.');
      } else {
        saved = await createMutation.mutateAsync({
          title: title.trim() || undefined,
          content: content.trim(),
          mood,
          tags: parsedTags,
          entry_date: entryDate,
          is_private: true,
        });
        setStatusMessage('New reflection saved securely.');
      }
      setSelectedEntry(saved);
      setIsEditing(false);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err: any) {
      setStatusMessage(`Error saving reflection: ${err.message || 'Unknown error'}`);
    }
  };

  const handleDeleteEntry = async (entryId: string) => {
    if (!window.confirm('Are you sure you want to permanently delete this private journal entry?')) {
      return;
    }
    try {
      await deleteMutation.mutateAsync(entryId);
      if (selectedEntry?.id === entryId) {
        setSelectedEntry(null);
        setIsEditing(false);
        setEditingEntryId(null);
      }
    } catch (err: any) {
      alert(`Failed to delete entry: ${err.message}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden text-slate-100">
      {/* Top Banner & Privacy Invariant Header */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/30 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-slate-100">Private Journaling &amp; Reflection</h1>
              <p className="text-xs text-slate-400">
                Distraction-free Markdown workspace for private daily reflections, mood tracking, and cognitive clarity.
              </p>
            </div>
          </div>
        </div>

        {/* Cryptographic Privacy Assurance Badge */}
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 text-xs">
          <Lock className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
          <span className="font-mono text-[11px]">Consent Protected: Cryptographically isolated from AI chat retrieval</span>
        </div>
      </div>

      {/* Main Workspace Body */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left Column: Entries List & Filters */}
        <div className="w-full md:w-80 lg:w-96 border-r border-slate-800 flex flex-col bg-slate-950">
          {/* Action Bar */}
          <div className="p-4 border-b border-slate-800/80 space-y-3">
            <button
              onClick={() => handleOpenNewEntry()}
              className="w-full flex items-center justify-center space-x-2 py-2 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs transition shadow-md shadow-indigo-600/20"
            >
              <Plus className="w-4 h-4" />
              <span>Write Reflection</span>
            </button>

            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search reflections..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            {/* Mood Filter Chips */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-[11px] scrollbar-none">
              <button
                onClick={() => setSelectedMood('')}
                className={`px-2 py-0.5 rounded-md font-medium border ${
                  selectedMood === ''
                    ? 'bg-slate-800 text-slate-100 border-slate-700'
                    : 'text-slate-400 border-transparent hover:text-slate-200'
                }`}
              >
                All
              </button>
              {MOOD_OPTIONS.map((m) => (
                <button
                  key={m.value}
                  onClick={() => setSelectedMood(selectedMood === m.value ? '' : m.value)}
                  className={`px-2 py-0.5 rounded-md font-medium border whitespace-nowrap ${
                    selectedMood === m.value
                      ? m.color
                      : 'text-slate-400 border-transparent hover:text-slate-200'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Entries Feed */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-800/40">
            {!user ? (
              <div className="p-8 text-center space-y-3">
                <Lock className="w-8 h-8 text-indigo-400 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
                  Sign in to create, browse, and sync your private reflection journal with cryptographic guarantees.
                </p>
              </div>
            ) : isLoading ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading reflections...</div>
            ) : error ? (
              <div className="p-4 m-3 bg-red-950/40 border border-red-800/80 rounded-lg text-xs text-red-300">
                Failed to load journal entries.
              </div>
            ) : !journalData?.items.length ? (
              <div className="p-8 text-center space-y-3">
                <BookOpen className="w-8 h-8 text-slate-600 mx-auto" />
                <p className="text-xs text-slate-400">No reflections recorded yet.</p>
                <p className="text-[11px] text-slate-500">
                  Reflections help clarify thoughts, track progress, and sharpen intuition.
                </p>
              </div>
            ) : (
              journalData.items.map((entry) => {
                const isSelected = selectedEntry?.id === entry.id;
                const moodObj = MOOD_OPTIONS.find((m) => m.value === entry.mood);
                return (
                  <div
                    key={entry.id}
                    onClick={() => handleSelectEntry(entry)}
                    className={`p-3.5 cursor-pointer transition select-none ${
                      isSelected
                        ? 'bg-indigo-950/30 border-l-2 border-l-indigo-500'
                        : 'hover:bg-slate-900/40'
                    }`}
                  >
                    <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1">
                      <span className="flex items-center space-x-1">
                        <Calendar className="w-3 h-3" />
                        <span>{entry.entry_date}</span>
                      </span>
                      {moodObj && (
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${moodObj.color}`}>
                          {moodObj.label}
                        </span>
                      )}
                    </div>
                    <h3 className="text-xs font-semibold text-slate-200 truncate mb-1">
                      {entry.title || 'Untitled Reflection'}
                    </h3>
                    <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                      {entry.content}
                    </p>
                    {entry.tags?.length > 0 && (
                      <div className="flex items-center gap-1 mt-2">
                        {entry.tags.slice(0, 3).map((tag, idx) => (
                          <span
                            key={idx}
                            className="text-[9px] px-1.5 py-0.2 rounded bg-slate-900 text-slate-400 border border-slate-800"
                          >
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Writing & Reflection Workspace */}
        <div className="flex-1 flex flex-col bg-slate-950 overflow-hidden">
          {isEditing ? (
            <form onSubmit={handleSaveEntry} className="flex-1 flex flex-col h-full overflow-hidden p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <div className="flex items-center space-x-2">
                  <Edit3 className="w-4 h-4 text-indigo-400" />
                  <span className="text-sm font-semibold text-slate-200">
                    {editingEntryId ? 'Edit Reflection' : 'New Reflection'}
                  </span>
                </div>
                <div className="flex items-center space-x-2">
                  {/* Write vs Preview Toggle */}
                  <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 mr-2">
                    <button
                      type="button"
                      onClick={() => setEditorTab('write')}
                      className={`px-2.5 py-1 text-xs font-medium rounded-md transition ${
                        editorTab === 'write'
                          ? 'bg-indigo-600 text-white'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Write
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditorTab('preview')}
                      className={`px-2.5 py-1 text-xs font-medium rounded-md transition flex items-center space-x-1 ${
                        editorTab === 'preview'
                          ? 'bg-indigo-600 text-white'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <Eye className="w-3 h-3" />
                      <span>Preview</span>
                    </button>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setIsEditing(false);
                      if (!selectedEntry && editingEntryId) {
                        setEditingEntryId(null);
                      }
                    }}
                    className="px-3 py-1.5 rounded-lg border border-slate-800 hover:bg-slate-900 text-slate-400 hover:text-slate-200 text-xs transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createMutation.isPending || updateMutation.isPending || !content.trim()}
                    className="flex items-center space-x-1.5 px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition shadow-md shadow-indigo-600/20 disabled:opacity-50"
                  >
                    <Save className="w-3.5 h-3.5" />
                    <span>Save</span>
                  </button>
                </div>
              </div>

              {statusMessage && (
                <div className="p-2.5 rounded-lg bg-indigo-950/40 border border-indigo-800/60 text-xs text-indigo-200 flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-indigo-400" />
                  <span>{statusMessage}</span>
                </div>
              )}

              {/* Title & Date Controls */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-2">
                  <input
                    type="text"
                    placeholder="Reflection title (optional)..."
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="w-full bg-slate-900/60 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <input
                    type="date"
                    value={entryDate}
                    onChange={(e) => setEntryDate(e.target.value)}
                    className="w-full bg-slate-900/60 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Mood and Tags Controls */}
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center space-x-1.5">
                  <Smile className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-xs text-slate-400">Mood:</span>
                  <select
                    value={mood}
                    onChange={(e) => setMood(e.target.value)}
                    className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                  >
                    {MOOD_OPTIONS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex-1 flex items-center space-x-1.5 min-w-[200px]">
                  <Tag className="w-3.5 h-3.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Tags (comma separated, e.g. strategy, health)"
                    value={tagsInput}
                    onChange={(e) => setTagsInput(e.target.value)}
                    className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Markdown Content Editor / Preview Tab */}
              <div className="flex-1 flex flex-col min-h-0">
                {editorTab === 'write' ? (
                  <textarea
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="Begin your reflection... Markdown formatting supported."
                    className="w-full flex-1 bg-slate-900/30 border border-slate-800 rounded-xl p-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 resize-none font-sans leading-relaxed"
                  />
                ) : (
                  <div className="w-full flex-1 bg-slate-900/30 border border-slate-800 rounded-xl p-6 overflow-y-auto">
                    {content.trim() ? (
                      <MessageContent content={content} role="assistant" />
                    ) : (
                      <div className="text-xs text-slate-500 italic">No content written yet to preview.</div>
                    )}
                  </div>
                )}
              </div>
            </form>
          ) : selectedEntry ? (
            /* Entry Detail View */
            <div className="flex-1 flex flex-col h-full overflow-hidden p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
                <div>
                  <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1">
                    <Calendar className="w-3.5 h-3.5" />
                    <span>{selectedEntry.entry_date}</span>
                    {selectedEntry.mood && (
                      <>
                        <span>•</span>
                        <span className="capitalize text-indigo-400">{selectedEntry.mood}</span>
                      </>
                    )}
                  </div>
                  <h2 className="text-lg font-bold text-slate-100">
                    {selectedEntry.title || 'Untitled Reflection'}
                  </h2>
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={() => handleStartEdit(selectedEntry)}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition shadow-md shadow-indigo-600/20"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                    <span>Edit</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeleteEntry(selectedEntry.id)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-900 transition text-xs border border-slate-800"
                    title="Delete Entry"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedEntry(null)}
                    className="px-3 py-1.5 rounded-lg border border-slate-800 hover:bg-slate-900 text-slate-400 hover:text-slate-200 text-xs transition"
                  >
                    Close
                  </button>
                </div>
              </div>

              {selectedEntry.tags && selectedEntry.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {selectedEntry.tags.map((tag, idx) => (
                    <span
                      key={idx}
                      className="text-[10px] px-2 py-0.5 rounded-md bg-slate-900 text-slate-300 border border-slate-800 font-mono"
                    >
                      #{tag}
                    </span>
                  ))}
                </div>
              )}

              {/* Rendered Markdown Body */}
              <div className="flex-1 overflow-y-auto pr-2">
                <div className="p-5 rounded-2xl bg-slate-900/30 border border-slate-800/80 leading-relaxed text-sm">
                  <MessageContent content={selectedEntry.content} role="assistant" />
                </div>
              </div>
            </div>
          ) : (
            /* Focused Welcome / Reflection Prompts Screen */
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center max-w-xl mx-auto space-y-6">
              <div className="p-3 rounded-2xl bg-gradient-to-tr from-purple-600/20 to-indigo-600/20 border border-purple-500/20 text-purple-400">
                <BookOpen className="w-8 h-8" />
              </div>

              <div className="space-y-2">
                <h2 className="text-lg font-bold text-slate-100">Daily Reflection &amp; Contemplation</h2>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Take a quiet moment to record your thoughts, decisions, and mindset. Your reflections are strictly isolated and never used to generate conversational memories without explicit consent.
                </p>
              </div>

              {/* Reflection Prompts Cards */}
              <div className="w-full space-y-2 text-left">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 flex items-center space-x-1">
                  <Sparkles className="w-3 h-3 text-indigo-400" />
                  <span>Inspiration Prompts for Today</span>
                </p>
                <div className="space-y-1.5">
                  {REFLECTION_PROMPTS.map((prompt, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleOpenNewEntry(prompt)}
                      className="w-full text-left p-3 rounded-xl bg-slate-900/50 hover:bg-slate-900 border border-slate-800/80 hover:border-slate-700 text-xs text-slate-300 transition flex items-center justify-between group"
                    >
                      <span className="leading-relaxed pr-2">{prompt}</span>
                      <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-indigo-400 flex-shrink-0 transition" />
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={() => handleOpenNewEntry()}
                className="flex items-center space-x-2 py-2.5 px-5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs transition shadow-lg shadow-indigo-600/20"
              >
                <Plus className="w-4 h-4" />
                <span>Start Blank Reflection</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
