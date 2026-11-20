/**
 * Projects Workspace View for AUREN Phase 3C.4 Productivity Core.
 * Groups tasks into coherent workspaces with derived task progress and deadline tracking.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React, { useState, useEffect } from 'react';
import {
  FolderKanban,
  Plus,
  Search,
  Clock,
  AlertCircle,
  Edit2,
  Trash2,
  ArrowLeft,
} from 'lucide-react';
import { useSafeSearch } from '../../hooks/useSafeSearch';
import { Project, ProjectCreateInput, ProjectUpdateInput } from '../../api/productivity';
import {
  useCreateProject,
  useDeleteProject,
  useProjects,
  useUpdateProject,
  useProject,
} from '../../hooks/useProductivity';
import { useAuth } from '../../context/AuthContext';
import { ProjectModal } from '../../components/productivity/ProjectModal';

export const ProjectsView: React.FC = () => {
  const { user } = useAuth();
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const searchParams = useSafeSearch<{ project_id?: string }>();
  const [activeProjectId, setActiveProjectId] = useState<string | null>(searchParams?.project_id || null);

  useEffect(() => {
    if (searchParams?.project_id && searchParams.project_id !== activeProjectId) {
      setActiveProjectId(searchParams.project_id);
    }
  }, [searchParams?.project_id]);

  const { data: projectsData, isLoading, error } = useProjects({
    status: selectedStatus || undefined,
    query: searchQuery || undefined,
    page,
    page_size: 20,
  }, user?.id);

  const { data: activeProjectDetail } = useProject(activeProjectId || undefined, user?.id);

  const createProjectMutation = useCreateProject(user?.id);
  const updateProjectMutation = useUpdateProject(user?.id);
  const deleteProjectMutation = useDeleteProject(user?.id);

  const handleOpenCreate = () => {
    setEditingProject(null);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (e: React.MouseEvent, project: Project) => {
    e.stopPropagation();
    setEditingProject(project);
    setIsModalOpen(true);
  };

  const handleDelete = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation();
    if (window.confirm('Delete this project? (Associated tasks will be unlinked and preserved)')) {
      await deleteProjectMutation.mutateAsync({ projectId, deleteTasks: false });
      if (activeProjectId === projectId) {
        setActiveProjectId(null);
      }
    }
  };

  const handleModalSubmit = async (data: ProjectCreateInput | ProjectUpdateInput) => {
    if (editingProject) {
      await updateProjectMutation.mutateAsync({ projectId: editingProject.id, input: data });
    } else {
      await createProjectMutation.mutateAsync(data as ProjectCreateInput);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#07080c] overflow-hidden text-slate-100">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between p-4 sm:p-6 border-b border-white/[0.06] bg-[#0e1017]/70 backdrop-blur-md gap-3 sm:gap-4">
        <div>
          <div className="flex items-center space-x-3.5">
            <div className="p-2.5 rounded-xl bg-champagne-500/10 border border-champagne-500/20 text-champagne-400 shadow-sm">
              <FolderKanban className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-xl font-bold tracking-tight text-white">Project Workspaces</h1>
                <span className="hidden sm:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-graphite-800/90 text-champagne-300 border border-champagne-500/20">
                  Execution Hub
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Group tasks, track milestone progress, and focus your execution.
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={handleOpenCreate}
          className="flex items-center justify-center space-x-2 px-4 py-2.5 min-h-[44px] bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-xs font-semibold rounded-xl transition-all shadow-md shadow-indigo-600/20 self-start md:self-auto touch-target cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>New Project</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 sm:p-6 pb-2 grid grid-cols-1 md:grid-cols-2 gap-2.5 sm:gap-3 border-b border-white/[0.06] bg-[#0e1017]/30">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search projects..."
            className="w-full pl-10 pr-3.5 py-2.5 bg-[#07080c] border border-white/[0.08] rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-champagne-500/50 transition min-h-[42px]"
          />
        </div>

        <div>
          <select
            value={selectedStatus}
            onChange={(e) => {
              setSelectedStatus(e.target.value);
              setPage(1);
            }}
            className="w-full px-3.5 py-2.5 bg-[#07080c] border border-white/[0.08] rounded-xl text-xs text-slate-300 focus:outline-none focus:border-champagne-500/50 transition min-h-[42px]"
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="planning">Planning</option>
            <option value="on_hold">On Hold</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>

      {/* Content Layout */}
      <div className="flex-1 flex overflow-hidden p-6 gap-6">
        {/* Project Cards Grid */}
        <div className={`flex-1 overflow-y-auto space-y-3.5 scrollbar-thin ${activeProjectId ? 'hidden lg:block' : ''}`}>
          {isLoading ? (
            <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
              <Clock className="w-5 h-5 animate-spin mr-2 text-champagne-400" />
              Loading projects...
            </div>
          ) : error ? (
            <div className="p-5 bg-[#0e1017]/60 border border-white/[0.08] rounded-2xl text-center space-y-2 shadow-sm">
              <AlertCircle className="w-5 h-5 text-champagne-400 mx-auto" />
              <div className="text-sm font-semibold text-slate-200">
                {!user ? 'Sign In to Access Projects' : 'Failed to load projects'}
              </div>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                {!user
                  ? 'Sign in or register to organize initiatives into structured projects and track execution.'
                  : 'Could not connect to the projects service. Please verify network connectivity and try again.'}
              </p>
            </div>
          ) : projectsData?.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 border border-dashed border-white/[0.08] rounded-2xl p-8 text-center bg-[#0e1017]/20">
              <FolderKanban className="w-12 h-12 text-slate-600 mb-3" />
              <h3 className="text-sm font-semibold text-slate-300">No projects yet</h3>
              <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4">
                Create a project to organize related tasks and track objective progress.
              </p>
              <button
                onClick={handleOpenCreate}
                className="px-4 py-2 bg-white/[0.06] hover:bg-white/[0.1] text-slate-200 text-xs font-medium rounded-xl transition-colors border border-white/[0.08] cursor-pointer"
              >
                Create Project
              </button>
            </div>
          ) : (
            projectsData?.items.map((project) => {
              const isActive = activeProjectId === project.id;
              const progress = project.task_count > 0 ? Math.round((project.completed_task_count / project.task_count) * 100) : 0;

              return (
                <div
                  key={project.id}
                  onClick={() => setActiveProjectId(project.id)}
                  className={`p-5 rounded-2xl border transition-all duration-200 cursor-pointer shadow-subtle-elevation ${
                    isActive
                      ? 'bg-[#0e1017] border-champagne-500/60 ring-1 ring-champagne-500/30'
                      : 'bg-[#0e1017]/70 border-white/[0.06] hover:border-champagne-500/30 hover:bg-[#0e1017]/95'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-semibold text-slate-100">{project.name}</span>
                        <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider bg-[#07080c] border border-white/[0.08] text-champagne-300/80 font-mono">
                          {project.status}
                        </span>
                      </div>
                      {project.description && (
                        <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">{project.description}</p>
                      )}
                    </div>

                    <div className="flex items-center space-x-1">
                      <button
                        onClick={(e) => handleOpenEdit(e, project)}
                        className="p-2 -m-1 sm:p-1.5 sm:m-0 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition touch-target flex items-center justify-center cursor-pointer"
                        title="Edit project"
                        aria-label="Edit project"
                      >
                        <Edit2 className="w-4 h-4 sm:w-3.5 sm:h-3.5" />
                      </button>
                      <button
                        onClick={(e) => handleDelete(e, project.id)}
                        className="p-2 -m-1 sm:p-1.5 sm:m-0 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-white/[0.06] transition touch-target flex items-center justify-center cursor-pointer"
                        title="Delete project"
                        aria-label="Delete project"
                      >
                        <Trash2 className="w-4 h-4 sm:w-3.5 sm:h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Progress Bar & Ratios */}
                  <div className="mt-4 pt-3 border-t border-white/[0.06]">
                    <div className="flex items-center justify-between text-xs mb-1.5 font-medium">
                      <span className="text-slate-400">{project.completed_task_count} / {project.task_count} tasks completed</span>
                      <span className="text-champagne-400 font-mono font-semibold">{progress}%</span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-[#07080c] overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-champagne-500 to-amber-400 rounded-full transition-all duration-300"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Project Detail Sidebar */}
        {activeProjectId && activeProjectDetail && (
          <div className="w-full lg:w-96 p-4 sm:p-5 rounded-2xl bg-[#0e1017]/90 border border-white/[0.08] flex flex-col space-y-4 shadow-subtle-elevation">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setActiveProjectId(null)}
                  className="lg:hidden p-1.5 -ml-1 text-slate-400 hover:text-white rounded-lg hover:bg-white/[0.06] touch-target flex items-center"
                  aria-label="Back to projects"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <h3 className="text-sm font-bold text-white tracking-tight">{activeProjectDetail.name}</h3>
              </div>
              <button
                onClick={() => setActiveProjectId(null)}
                className="px-2.5 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-white/[0.06] transition touch-target flex items-center"
              >
                Close
              </button>
            </div>
            {activeProjectDetail.description && (
              <p className="text-xs text-slate-400 leading-relaxed">{activeProjectDetail.description}</p>
            )}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono">Tasks in Workspace</h4>
              {activeProjectDetail.tasks && activeProjectDetail.tasks.length > 0 ? (
                <div className="space-y-1.5">
                  {activeProjectDetail.tasks.map((t) => (
                    <div key={t.id} className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06] text-xs text-slate-200 flex items-center justify-between">
                      <span className="truncate">{t.title}</span>
                      <span className="text-[10px] uppercase font-mono text-slate-500">{t.status}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500 italic">No tasks linked to this project yet.</p>
              )}
            </div>
          </div>
        )}
      </div>

      <ProjectModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleModalSubmit}
        initialProject={editingProject}
      />
    </div>
  );
};
