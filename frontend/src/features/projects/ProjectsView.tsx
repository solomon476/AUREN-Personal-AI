/**
 * Projects Workspace View for AUREN Phase 3C.4 Productivity Core.
 * Groups tasks into coherent workspaces with derived task progress and deadline tracking.
 */

import React, { useState } from 'react';
import {
  FolderKanban,
  Plus,
  Search,
  Clock,
  CheckCircle2,
  AlertCircle,
  Edit2,
  Trash2,
  ListTodo,
} from 'lucide-react';
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
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

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
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden text-slate-100">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between p-6 border-b border-slate-800 bg-slate-900/40 gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <FolderKanban className="w-5 h-5" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100">Project Workspaces</h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Group tasks, track milestone progress, and focus your execution.
          </p>
        </div>

        <button
          onClick={handleOpenCreate}
          className="flex items-center justify-center space-x-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-indigo-600/20 self-start md:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>New Project</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-6 pb-2 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search projects..."
            className="w-full pl-9 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div>
          <select
            value={selectedStatus}
            onChange={(e) => {
              setSelectedStatus(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
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
        <div className={`flex-1 overflow-y-auto space-y-3 ${activeProjectId ? 'hidden lg:block' : ''}`}>
          {isLoading ? (
            <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
              <Clock className="w-5 h-5 animate-spin mr-2" />
              Loading projects...
            </div>
          ) : error ? (
            <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl text-center space-y-2">
              <AlertCircle className="w-5 h-5 text-indigo-400 mx-auto" />
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
            <div className="flex flex-col items-center justify-center h-64 border border-dashed border-slate-800 rounded-xl p-8 text-center bg-slate-900/20">
              <FolderKanban className="w-12 h-12 text-slate-600 mb-3" />
              <h3 className="text-sm font-semibold text-slate-300">No projects yet</h3>
              <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4">
                Create a project to organize related tasks and track objective progress.
              </p>
              <button
                onClick={handleOpenCreate}
                className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg transition-colors border border-slate-700"
              >
                Create Project
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {projectsData?.items.map((project) => {
                const isSelected = activeProjectId === project.id;

                return (
                  <div
                    key={project.id}
                    onClick={() => setActiveProjectId(isSelected ? null : project.id)}
                    className={`group relative p-4 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                      isSelected
                        ? 'bg-slate-900 border-indigo-500/80 ring-1 ring-indigo-500/30'
                        : 'bg-slate-900/60 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900'
                    }`}
                  >
                    <div>
                      {/* Color Tab Header */}
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <span
                            className="w-3 h-3 rounded-full"
                            style={{ backgroundColor: project.color || '#4872bd' }}
                          />
                          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                            {project.status}
                          </span>
                        </div>

                        <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => handleOpenEdit(e, project)}
                            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                            title="Edit Project"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={(e) => handleDelete(e, project.id)}
                            className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800"
                            title="Delete Project"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>

                      <h3 className="text-base font-semibold text-slate-100 group-hover:text-indigo-300 transition-colors">
                        {project.name}
                      </h3>

                      {project.description && (
                        <p className="text-xs text-slate-400 mt-1 line-clamp-2">{project.description}</p>
                      )}
                    </div>

                    {/* Progress Bar & Task Count */}
                    <div className="mt-4 pt-3 border-t border-slate-800/60">
                      <div className="flex items-center justify-between text-xs mb-1.5">
                        <span className="text-slate-400 flex items-center">
                          <ListTodo className="w-3.5 h-3.5 mr-1 text-slate-500" />
                          {project.completed_task_count} / {project.task_count} tasks completed
                        </span>
                        <span className="font-semibold text-slate-200">
                          {project.progress_percentage}%
                        </span>
                      </div>

                      <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-300"
                          style={{
                            width: `${project.progress_percentage}%`,
                            backgroundColor: project.color || '#4872bd',
                          }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Project Detail Drawer */}
        {activeProjectId && activeProjectDetail && (
          <div className="w-full lg:w-96 flex flex-col bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden p-5 animate-in slide-in-from-right duration-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <span
                  className="w-3.5 h-3.5 rounded-full"
                  style={{ backgroundColor: activeProjectDetail.color || '#4872bd' }}
                />
                <h3 className="font-semibold text-slate-100">{activeProjectDetail.name}</h3>
              </div>
              <button
                onClick={() => setActiveProjectId(null)}
                className="text-xs text-slate-400 hover:text-slate-200"
              >
                Close
              </button>
            </div>

            <div className="py-3 text-xs text-slate-400 border-b border-slate-800">
              {activeProjectDetail.description || 'No description provided.'}
            </div>

            <div className="flex-1 overflow-y-auto py-3 space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Project Tasks ({activeProjectDetail.tasks.length})
              </h4>
              {activeProjectDetail.tasks.length === 0 ? (
                <div className="text-xs text-slate-500 py-4 text-center">
                  No tasks assigned to this project yet.
                </div>
              ) : (
                activeProjectDetail.tasks.map((task) => (
                  <div
                    key={task.id}
                    className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center space-x-2 truncate">
                      {task.status === 'completed' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border border-slate-600 flex-shrink-0" />
                      )}
                      <span
                        className={`truncate ${
                          task.status === 'completed' ? 'line-through text-slate-500' : 'text-slate-200'
                        }`}
                      >
                        {task.title}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 uppercase ml-2 flex-shrink-0">
                      {task.priority}
                    </span>
                  </div>
                ))
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

