import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';

// Layouts & Guards
import MainLayout from '../components/layout/MainLayout';
import ProtectedRoute from '../components/layout/ProtectedRoute';

// Auth Pages
import LoginPage from '../features/auth/LoginPage';
import ActivateAccountPage from '../features/auth/ActivateAccountPage';

// Feature Pages
import DashboardRouter from '../features/dashboard/DashboardRouter';
import AttendancePortal from '../features/attendance/AttendancePortal';
import LeavePortal from '../features/leaves/LeavePortal';
import SkillMatrixView from '../features/skills/SkillMatrixView';
import WorkDiaryView from '../features/workDiary/WorkDiaryView';
import ProjectListView from '../features/projects/ProjectListView';
import PayrollCenter from '../features/payroll/PayrollCenter';
import AssetsInventory from '../features/enterprise/AssetsInventory';
import ComplaintListView from '../features/helpdesk/ComplaintListView';
import CelebrationsView from '../features/holidays/CelebrationsView';
import AdminControlCenter from '../features/admin/AdminControlCenter';
import TeamDirectoryView from '../features/admin/TeamDirectoryView';

export const router = createBrowserRouter([
  // Public Auth Routes
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/activate',
    element: <ActivateAccountPage />,
  },

  // Protected App Routes
  {
    path: '/',
    element: <ProtectedRoute />,
    children: [
      {
        element: <MainLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="/dashboard" replace />,
          },
          {
            path: 'dashboard',
            element: <DashboardRouter />,
          },
          {
            path: 'attendance',
            element: <AttendancePortal />,
          },
          {
            path: 'leaves',
            element: <LeavePortal />,
          },
          {
            path: 'skills',
            element: <SkillMatrixView />,
          },
          {
            path: 'work-diary',
            element: <WorkDiaryView />,
          },
          {
            path: 'projects',
            element: <ProjectListView />,
          },
          {
            path: 'payroll',
            element: <PayrollCenter />,
          },
          {
            path: 'enterprise',
            element: <AssetsInventory />,
          },
          {
            path: 'helpdesk',
            element: <ComplaintListView />,
          },
          {
            path: 'celebrations',
            element: <CelebrationsView />,
          },
          {
            path: 'directory',
            element: <TeamDirectoryView />,
          },
          {
            path: 'admin',
            element: <AdminControlCenter />,
          },
        ],
      },
    ],
  },

  // Fallback
  {
    path: '*',
    element: <Navigate to="/dashboard" replace />,
  },
]);

export default router;

