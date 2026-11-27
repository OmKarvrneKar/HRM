import React from 'react';
import { useAuth } from '../../hooks/useAuth';
import EmployeeDashboard from './EmployeeDashboard';
import TeamLeadDashboard from './TeamLeadDashboard';
import ManagerDashboard from './ManagerDashboard';
import HRDashboard from './HRDashboard';
import AdminDashboard from './AdminDashboard';

export const DashboardRouter = () => {
  const { role } = useAuth();
  const normalizedRole = (role || 'employee').toLowerCase();

  switch (normalizedRole) {
    case 'admin':
      return <AdminDashboard />;
    case 'hr':
      return <HRDashboard />;
    case 'manager':
      return <ManagerDashboard />;
    case 'tl':
    case 'team_lead':
      return <TeamLeadDashboard />;
    case 'employee':
    default:
      return <EmployeeDashboard />;
  }
};

export default DashboardRouter;

